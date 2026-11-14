import csv
import json
import os
import shutil
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import rasterio
import yaml
from PIL import Image
from rasterio.transform import from_origin

from contracts.models.common import Provenance
from route.answer_key import FrameSource, KeyFrame, save_answer

PROJECTION = "+proj=eqc +lat_ts=18.4663 +lon_0=0 +R=3396190 +units=m +no_defs"
PHOTO_PAIRS = [[10, 10], [110, 10], [110, 90], [10, 90]]
MAP_PAIRS = [
    [4354020, 1092220],
    [4354020, 1092020],
    [4353860, 1092020],
    [4353860, 1092220],
]


@pytest.fixture
def frame(tmp_path):
    pack = tmp_path / "jezero" / "pack"
    pack.mkdir(parents=True)
    photo = np.arange(101 * 121, dtype=np.uint8).reshape(101, 121)
    photo_path = pack / "frame.png"
    Image.fromarray(photo).save(photo_path)
    source = pack / "source.txt"
    source.write_bytes(b"abc")
    crop = pack / "flight-09.tif"
    with rasterio.open(
        crop,
        "w",
        driver="GTiff",
        width=150,
        height=150,
        count=1,
        dtype="uint8",
        crs=PROJECTION,
        transform=from_origin(4353800, 1092300, 2, 2),
    ) as dst:
        dst.write(np.full((150, 150), 100, dtype=np.uint8), 1)
    return KeyFrame(
        source=FrameSource(
            photo_id="frame-09",
            flight=9,
            projection=PROJECTION,
            crop=crop,
            inputs=(photo_path, source),
        ),
        image=photo,
        valid=np.ones(photo.shape, dtype=bool),
        reference_px=(60, 50),
        heading_deg=0,
    )


def test_saved_key_keeps_the_pairs_tags_sources_and_flights_apart_from_the_pack(tmp_path, frame):
    path = save_answer(
        tmp_path,
        frame,
        PHOTO_PAIRS,
        MAP_PAIRS,
        terrain_type="textured",
        hard_mode=True,
        reviewed=True,
        simulated=True,
    )

    key = json.loads(path.read_text())
    assert path == tmp_path / "jezero" / "answer-key" / "keys" / "frame-09.json"
    assert key["true_position"] == pytest.approx({"x": 4353940, "y": 1092120})
    assert key["true_heading_deg"] == pytest.approx(90)
    assert (key["terrain_type"], key["hard_mode"], key["checked_by_eye"], key["simulated"]) == (
        "textured",
        True,
        True,
        True,
    )
    assert key["tie_points"] == [
        {"photo_px": photo, "map_xy": position}
        for photo, position in zip(PHOTO_PAIRS, MAP_PAIRS, strict=True)
    ]
    assert key["projection"] == PROJECTION
    provenance = Provenance.model_validate(key["provenance"])
    assert provenance.script == "route/key_frames.py"
    assert provenance.commit
    assert {item.path for item in provenance.inputs} == {
        "jezero/pack/frame.png",
        "jezero/pack/source.txt",
        "jezero/pack/flight-09.tif",
    }
    assert next(i.sha256 for i in provenance.inputs if i.path.endswith("source.txt")) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    with Image.open(tmp_path / key["overlay"]) as overlay:
        assert overlay.format == "PNG"
        assert overlay.width > 500 and overlay.height > 200
    flights = json.loads((path.parent.parent / "flights.json").read_text())
    assert flights["excluded_flights"] == [9]
    assert flights["photo_ids"] == ["frame-09"]


def test_a_point_outside_the_visible_photo_cannot_become_an_answer_key(tmp_path, frame):
    frame.valid[10, 10] = False

    with pytest.raises(ValueError, match="visible"):
        save_answer(
            tmp_path,
            frame,
            PHOTO_PAIRS,
            MAP_PAIRS,
            terrain_type="textured",
            hard_mode=False,
            reviewed=True,
            simulated=True,
        )

    assert not (tmp_path / "jezero" / "answer-key").exists()


def test_points_outside_the_map_crop_cannot_become_an_answer_key(tmp_path, frame):
    outside = np.asarray(MAP_PAIRS) + [1000, 0]

    with pytest.raises(ValueError, match="visible map"):
        save_answer(
            tmp_path,
            frame,
            PHOTO_PAIRS,
            outside,
            terrain_type="plain",
            hard_mode=True,
            reviewed=True,
            simulated=True,
        )

    assert not (tmp_path / "jezero" / "answer-key").exists()


def test_an_unreviewed_overlay_cannot_become_an_answer_key(tmp_path, frame):
    with pytest.raises(ValueError, match="check the overlay"):
        save_answer(
            tmp_path,
            frame,
            PHOTO_PAIRS,
            MAP_PAIRS,
            terrain_type="plain",
            hard_mode=True,
            reviewed=False,
            simulated=True,
        )

    assert not (tmp_path / "jezero" / "answer-key").exists()


def test_an_existing_key_is_never_replaced_and_every_keyed_flight_is_excluded(tmp_path, frame):
    tags = {"terrain_type": "plain", "hard_mode": True, "reviewed": True, "simulated": True}
    first = save_answer(tmp_path, frame, PHOTO_PAIRS, MAP_PAIRS, **tags)
    original = first.read_bytes()

    with pytest.raises(FileExistsError, match="nothing was replaced"):
        save_answer(tmp_path, frame, PHOTO_PAIRS, MAP_PAIRS, **tags)
    save_answer(
        tmp_path,
        replace(frame, source=replace(frame.source, photo_id="frame-10", flight=10)),
        PHOTO_PAIRS,
        MAP_PAIRS,
        **tags,
    )

    assert first.read_bytes() == original
    flights = json.loads((first.parent.parent / "flights.json").read_text())
    assert flights["excluded_flights"] == [9, 10]
    assert flights["photo_ids"] == ["frame-09", "frame-10"]


@pytest.mark.parametrize("failure", [OSError, KeyboardInterrupt])
@pytest.mark.parametrize("partial", [False, True])
def test_a_failed_key_write_leaves_no_overlay_that_would_block_retry(
    tmp_path, frame, monkeypatch, failure, partial
):
    original_open = Path.open
    tags = {"terrain_type": "plain", "hard_mode": True, "reviewed": True, "simulated": True}

    def failed_open(path, mode="r", *args, **kwargs):
        if path.name == "frame-09.json" and "x" in mode:
            if partial:
                with original_open(path, mode, *args, **kwargs) as output:
                    output.write(b'{"photo_id":')
            raise failure("simulated write failure")
        return original_open(path, mode, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", failed_open)
        with pytest.raises(failure, match="simulated write failure"):
            save_answer(tmp_path, frame, PHOTO_PAIRS, MAP_PAIRS, **tags)

    folder = tmp_path / "jezero" / "answer-key"
    assert not (folder / "keys" / "frame-09.json").exists()
    assert not (folder / "overlays" / "frame-09.png").exists()
    assert save_answer(tmp_path, frame, PHOTO_PAIRS, MAP_PAIRS, **tags).is_file()


@pytest.mark.parametrize(
    "damage", ["truncated", "empty_record", "orphan_overlay", "missing_overlay", "corrupt_overlay"]
)
def test_resuming_preserves_incomplete_outputs_and_allows_rekeying(tmp_path, frame, damage):
    from route.answer_key import answer_is_saved

    tags = {"terrain_type": "plain", "hard_mode": True, "reviewed": True, "simulated": True}
    path = save_answer(tmp_path, frame, PHOTO_PAIRS, MAP_PAIRS, **tags)
    overlay = tmp_path / "jezero" / "answer-key" / "overlays" / "frame-09.png"
    if damage == "truncated":
        path.write_bytes(b'{"photo_id":')
    elif damage == "empty_record":
        path.write_bytes(b"{}")
    elif damage == "orphan_overlay":
        path.unlink()
    elif damage == "missing_overlay":
        overlay.unlink()
    else:
        overlay.write_bytes(b"not a PNG")
    damaged = {p.name: p.read_bytes() for p in (path, overlay) if p.exists()}

    with pytest.warns(UserWarning, match="incomplete"):
        assert not answer_is_saved(tmp_path, frame.source.photo_id)

    recovered = path.parent.parent / "incomplete"
    assert {p.name: p.read_bytes() for p in recovered.glob("*/*")} == damaged
    assert not path.exists() and not overlay.exists()
    saved = save_answer(tmp_path, frame, PHOTO_PAIRS, MAP_PAIRS, **tags)
    before = saved.read_bytes()
    assert answer_is_saved(tmp_path, frame.source.photo_id)
    assert saved.read_bytes() == before


def test_a_read_error_never_quarantines_a_valid_key(tmp_path, frame, monkeypatch):
    from route.answer_key import answer_is_saved

    tags = {"terrain_type": "plain", "hard_mode": True, "reviewed": True, "simulated": True}
    key = save_answer(tmp_path, frame, PHOTO_PAIRS, MAP_PAIRS, **tags)
    before = key.read_bytes()
    original_open = Path.open

    def unreadable(path, mode="r", *args, **kwargs):
        if path == key and "r" in mode:
            raise OSError("temporary read failure")
        return original_open(path, mode, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", unreadable)
        with pytest.raises(OSError, match="temporary read failure"):
            answer_is_saved(tmp_path, frame.source.photo_id)

    assert key.read_bytes() == before
    assert not (key.parent.parent / "incomplete").exists()


def test_resuming_never_moves_another_writers_in_progress_overlay(tmp_path, frame, monkeypatch):
    from route.answer_key import answer_is_saved

    publish = Path.rename if os.name == "nt" else os.link

    def resume_during_publish(source, destination):
        result = publish(source, destination)
        if Path(destination).parent.name == "overlays":
            with pytest.raises(OSError):
                answer_is_saved(tmp_path, frame.source.photo_id)
        return result

    if os.name == "nt":
        monkeypatch.setattr(Path, "rename", resume_during_publish)
    else:
        monkeypatch.setattr(os, "link", resume_during_publish)
    key = save_answer(
        tmp_path,
        frame,
        PHOTO_PAIRS,
        MAP_PAIRS,
        terrain_type="plain",
        hard_mode=True,
        reviewed=True,
        simulated=True,
    )

    assert answer_is_saved(tmp_path, frame.source.photo_id)
    assert not (key.parent.parent / "incomplete").exists()


@pytest.mark.parametrize("destination_folder", ["overlays", "keys"])
@pytest.mark.parametrize("after", [False, True])
def test_interrupting_publication_never_commits_partial_json_or_overwrites_a_saved_key(
    tmp_path, frame, monkeypatch, destination_folder, after
):
    from route.answer_key import answer_is_saved

    publish = Path.rename if os.name == "nt" else os.link

    def interrupted(source, destination):
        selected = Path(destination).parent.name == destination_folder
        if selected and not after:
            raise KeyboardInterrupt("publication interrupted")
        result = publish(source, destination)
        if selected and after:
            raise KeyboardInterrupt("publication interrupted")
        return result

    tags = {"terrain_type": "plain", "hard_mode": True, "reviewed": True, "simulated": True}
    with monkeypatch.context() as patch:
        if os.name == "nt":
            patch.setattr(Path, "rename", interrupted)
        else:
            patch.setattr(os, "link", interrupted)
        with pytest.raises(KeyboardInterrupt, match="publication interrupted"):
            save_answer(tmp_path, frame, PHOTO_PAIRS, MAP_PAIRS, **tags)

    committed = destination_folder == "keys" and after
    assert answer_is_saved(tmp_path, frame.source.photo_id) == committed
    if committed:
        path = tmp_path / "jezero" / "answer-key" / "keys" / "frame-09.json"
        before = path.read_bytes()
        with pytest.raises(FileExistsError, match="nothing was replaced"):
            save_answer(tmp_path, frame, PHOTO_PAIRS, MAP_PAIRS, **tags)
        assert path.read_bytes() == before
    else:
        path = save_answer(tmp_path, frame, PHOTO_PAIRS, MAP_PAIRS, **tags)
    assert json.loads(path.read_text())["true_position"] == {
        "x": pytest.approx(4353940),
        "y": pytest.approx(1092120),
    }
    assert answer_is_saved(tmp_path, frame.source.photo_id)


def test_no_data_on_the_map_cannot_be_a_tie_point(tmp_path, frame):
    with rasterio.open(frame.source.crop, "r+") as crop:
        values = crop.read(1)
        values[40, 110] = 0
        crop.nodata = 0
        crop.write(values, 1)

    with pytest.raises(ValueError, match="visible map"):
        save_answer(
            tmp_path,
            frame,
            PHOTO_PAIRS,
            MAP_PAIRS,
            terrain_type="plain",
            hard_mode=True,
            reviewed=True,
            simulated=True,
        )

    assert not (tmp_path / "jezero" / "answer-key").exists()


def test_the_delivered_pack_loads_a_rectified_view_and_preserves_its_source_files(tmp_path, frame):
    from route.answer_key import load_key_frame, read_pack

    pack = tmp_path / "jezero" / "pack"
    frames = pack / "frames"
    frames.mkdir()
    label_name = "HNM_0152_0680432615_348FDR_N0100001HELI03026_0000LUJ05"
    photo = np.tile(np.arange(640, dtype=np.uint8), (480, 1))
    Image.fromarray(photo).save(frames / f"{label_name}.png")
    labels = tmp_path / "jezero" / "source" / "helicam" / "sol-00152"
    labels.mkdir(parents=True)
    fixture = Path(__file__).parents[2] / "prep" / "tests" / "fixtures" / f"{label_name}.xml"
    shutil.copyfile(fixture, labels / fixture.name)
    with (pack / "frames.csv").open("w", newline="") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=["flight", "sol", "frame_png", "product", "crop", "hard_mode"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "flight": 10,
                "sol": 152,
                "frame_png": f"{label_name}.png",
                "product": f"{label_name}.IMG",
                "crop": frame.source.crop.name,
                "hard_mode": "True",
            }
        )
    site_path = tmp_path / "jezero.yaml"
    site_path.write_text(
        yaml.safe_dump(
            {
                "site": "jezero",
                "name": "Synthetic pack",
                "projection": PROJECTION,
                "bounds": {
                    "min_x": 4353800,
                    "min_y": 1092000,
                    "max_x": 4354100,
                    "max_y": 1092300,
                },
                "habitat": None,
                "base_camp": None,
                "science_targets": [],
                "checkpoints": [],
                "files": {
                    "frame_list": "jezero/pack/frames.csv",
                    "crop_flight_10": frame.source.crop.relative_to(tmp_path).as_posix(),
                },
                "replayed_sol": None,
            }
        )
    )

    choices = read_pack(tmp_path, site_path)
    loaded = load_key_frame(choices[0])

    assert len(choices) == 1
    assert (loaded.source.photo_id, loaded.source.flight, choices[0].hard_mode) == (
        label_name,
        10,
        True,
    )
    assert loaded.reference_px == (127.5, 127.5)
    assert loaded.image.shape == loaded.valid.shape == (256, 256)
    assert loaded.valid.any() and not loaded.valid.all()
    assert loaded.source.projection == PROJECTION
    assert set(loaded.source.inputs) == {
        frames / f"{label_name}.png",
        labels / f"{label_name}.xml",
        pack / "frames.csv",
        site_path,
    }


def test_clicking_four_pairs_and_reviewing_the_overlay_saves_the_tagged_key(tmp_path, frame):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib.backend_bases import MouseEvent

    from route.key_frames import KeyingWindow

    window = KeyingWindow(tmp_path, frame, hard_mode=True, simulated=True)
    window.figure.canvas.draw()

    def click(ax, point, transform=None):
        x, y = (transform or ax.transData).transform(point)
        for name in ("button_press_event", "button_release_event"):
            event = MouseEvent(name, window.figure.canvas, x, y, button=1)
            window.figure.canvas.callbacks.process(name, event)

    for photo, position in zip(PHOTO_PAIRS, MAP_PAIRS, strict=True):
        click(window.photo_ax, photo)
        click(window.map_ax, position)
    window.terrain.set_active(1)
    click(window.save_button.ax, (0.5, 0.5), window.save_button.ax.transAxes)
    assert not (tmp_path / "jezero" / "answer-key").exists()
    window.checks.set_active(1)
    click(window.preview_button.ax, (0.5, 0.5), window.preview_button.ax.transAxes)
    assert not window.checks.get_status()[1]
    window.checks.set_active(1)
    click(window.save_button.ax, (0.5, 0.5), window.save_button.ax.transAxes)

    path = tmp_path / "jezero" / "answer-key" / "keys" / "frame-09.json"
    saved = json.loads(path.read_text())
    assert saved["true_position"] == pytest.approx({"x": 4353940, "y": 1092120}, abs=0.01)
    assert saved["true_heading_deg"] == pytest.approx(90, abs=0.01)
    assert saved["terrain_type"] == "textured"
    assert saved["checked_by_eye"] and saved["hard_mode"] and saved["simulated"]
