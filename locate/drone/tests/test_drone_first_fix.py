"""Reject invalid previous photos before reading a fix or loading a matcher."""

import csv
from pathlib import Path

import pytest

from locate.drone import first_fix

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
