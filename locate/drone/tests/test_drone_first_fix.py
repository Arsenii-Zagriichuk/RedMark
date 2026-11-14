"""Check prior validation and how the runner publishes fixes and overlays."""

import csv
import hashlib
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from contracts.models.fix_result import FixResult
from locate.drone import first_fix, records
from locate.drone.fix import DroneFix, GroundView, MapWindow

FRAME = "HNM_0152_0680432615_348FDR_N0100001HELI03026_0000LUJ05"
LABEL = Path(__file__).parents[3] / "prep" / "tests" / "fixtures" / f"{FRAME}.xml"


@pytest.mark.parametrize(
    ("previous", "flight", "clock", "error"),
    [
        (FRAME, 10, "680432615.348227", "must precede the current photo"),
        ("later", 10, "680432616.348227", "must precede the current photo"),
        ("other-flight", 9, "680432614.348227", "must be from the same flight"),
    ],
)
def test_run_rejects_invalid_previous_photo(tmp_path, monkeypatch, previous, flight, clock, error):
    jezero = tmp_path / "jezero"
    labels = jezero / "source" / "helicam" / "sol-00152"
    labels.mkdir(parents=True)
    label = LABEL.read_text()
    (labels / LABEL.name).write_text(label)
    rows = [(FRAME, 10, 152, "flight-10.tif")]
    if previous != FRAME:
        prior_label = (
            label.replace(f"{FRAME}.IMG", f"{previous}.IMG")
            .replace("HELI_G_FRAME_10", f"HELI_G_FRAME_{flight}")
            .replace("HELI_M_FRAME_10", f"HELI_M_FRAME_{flight}")
            .replace("680432615.348227", clock)
        )
        (labels / f"{previous}.xml").write_text(prior_label)
        rows.append((previous, flight, 152, f"flight-{flight}.tif"))
    pack = jezero / "pack"
    pack.mkdir()
    with (pack / "frames.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["product", "flight", "sol", "crop"])
        writer.writerows((f"{stem}.IMG", f, sol, crop) for stem, f, sol, crop in rows)

    monkeypatch.setattr(first_fix, "data_root", lambda: tmp_path)
    monkeypatch.setattr(first_fix, "RESULTS", tmp_path / "results")
    with pytest.raises(SystemExit, match=error):
        first_fix.run(FRAME, "loftr", previous)


def test_retry_preserves_published_overlay_and_hashes_the_prior_used(tmp_path, monkeypatch):
    root = tmp_path / "data"
    pack = root / "jezero" / "pack"
    pack.mkdir(parents=True)
    (pack / "frames.csv").write_text(
        "product,flight,sol,crop,hard_mode\n"
        "prior.IMG,10,152,flight-10.tif,False\n"
        "target.IMG,10,152,flight-10.tif,False\n"
    )
    (pack / "crops").mkdir()
    (pack / "crops" / "flight-10.tif").touch()
    labels = root / "jezero" / "source" / "helicam" / "sol-00152"
    labels.mkdir(parents=True)
    for stem, clock in (("prior", "1"), ("target", "2")):
        (labels / f"{stem}.xml").write_text(clock)
        (labels / f"{stem}.IMG").touch()
    waypoints = root / "jezero" / "source" / "nasa"
    waypoints.mkdir()
    (waypoints / "m20_heli_waypoints.json").touch()
    weights = root / first_fix.JPL_LOFTR_WEIGHTS
    weights.parent.mkdir(parents=True)
    weights.touch()

    results = tmp_path / "results" / "drone"
    monkeypatch.setattr(first_fix, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(first_fix, "RESULTS", results)
    monkeypatch.setattr(first_fix, "__file__", str(tmp_path / "first_fix.py"))
    monkeypatch.setattr(first_fix, "data_root", lambda: root)
    monkeypatch.setattr(records, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(records, "data_root", lambda: root)
    monkeypatch.setattr(
        records.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout="")
    )
    monkeypatch.setattr(
        first_fix, "read_drone_frame", lambda label: SimpleNamespace(flight=10, sclk=int(label))
    )
    monkeypatch.setattr(first_fix, "_onboard", lambda frame, waypoints: (10.0, 20.0))
    monkeypatch.setattr(first_fix, "pick_device", lambda: SimpleNamespace(type="cpu"))
    monkeypatch.setattr(first_fix, "loftr_matcher", lambda weights, device: None)
    pixels = np.full((8, 8), 127, dtype=np.uint8)
    raw = nullcontext(SimpleNamespace(read=lambda band: pixels))
    monkeypatch.setattr(first_fix.rasterio, "open", lambda path: raw)
    ground = GroundView(pixels, pixels > 0, 0.25, np.array([3.5, 3.5]), 0.0)
    window = MapWindow(pixels, 9.0, 21.0, 0.25)

    def fit_at(centre):
        points = np.array([centre])
        return ground, window, DroneFix(centre, 0.0, 15, 15, 1.0, 0.0, points, points, (1, 0))

    monkeypatch.setattr(
        first_fix, "fix_frame", lambda raw, frame, crop, centre, matcher: fit_at(centre)
    )
    first_fix.run("prior", "loftr", None)
    prior_path = results / "fixes" / "prior.json"
    prior_bytes = prior_path.read_bytes()

    def fit_after_prior_replacement(raw, frame, crop, centre, matcher):
        # Simulate a rerun publishing a new prior after the target read the original.
        new_prior = FixResult.model_validate_json(prior_bytes)
        new_prior.position.x = 11.0
        staged = prior_path.with_suffix(".tmp")
        staged.write_text(new_prior.model_dump_json())
        staged.replace(prior_path)
        assert centre == (10.0, 20.0)
        return fit_at(centre)

    monkeypatch.setattr(first_fix, "fix_frame", fit_after_prior_replacement)
    first_fix.run("target", "loftr", "prior")
    target_path = results / "fixes" / "target.json"
    published = FixResult.model_validate_json(target_path.read_bytes())
    inputs = {entry.path: entry.sha256 for entry in published.provenance.inputs}
    assert inputs["results/drone/fixes/prior.json"] == hashlib.sha256(prior_bytes).hexdigest()

    monkeypatch.setattr(
        first_fix, "fix_frame", lambda raw, frame, crop, centre, matcher: fit_at(centre)
    )
    replace = Path.replace

    def fail_target_publish(path, destination):
        if destination == target_path:
            raise OSError("cannot publish fix")
        return replace(path, destination)

    monkeypatch.setattr(Path, "replace", fail_target_publish)
    with pytest.raises(OSError, match="cannot publish fix"):
        first_fix.run("target", "loftr", "prior")

    assert FixResult.model_validate_json(target_path.read_bytes()) == published
    with Image.open(tmp_path / published.overlay) as overlay:
        assert FixResult.model_validate_json(overlay.info["fix_result"]) == published
