"""Seam: which ground each flight's crop covers and which frames go in the pack."""

import json
from pathlib import Path

import pytest

from prep.jezero.flights import flight_bounds, load_flights
from prep.jezero.frames import NavcamFrame, choose_frames, navcam_products, read_label

FIXTURES = Path(__file__).parent / "fixtures"
LABEL = FIXTURES / "HNM_0152_0680432615_348FDR_N0100001HELI03026_0000LUJ05.xml"


def test_flights_load_with_their_sol_and_a_site_frame_track():
    flights = load_flights(FIXTURES / "m20_heli_flight_path.json")

    assert sorted(flights) == [9, 10]
    assert flights[10].sol == 152
    # Flight 10 took off where flight 9 landed: NASA's waypoint file gives
    # that spot (flight 9's landing) as Easting 4354187.8, Northing 1092319.7.
    waypoints = json.loads((FIXTURES / "m20_heli_waypoints.json").read_text())["features"]
    flight_9_end = next(f["properties"] for f in waypoints if f["properties"]["Flight"] == 9)
    x, y = flights[10].path[0]
    assert x == pytest.approx(flight_9_end["Easting"], abs=1.0)
    assert y == pytest.approx(flight_9_end["Northing"], abs=1.0)


def test_flight_bounds_add_the_margin_on_every_side():
    path = [(100.0, 50.0), (400.0, 20.0), (250.0, 90.0)]

    assert flight_bounds(path, margin=200.0) == (-100.0, -180.0, 600.0, 290.0)


def test_navcam_products_are_the_full_frames_of_one_sol():
    lines = (FIXTURES / "collection_data_inventory.csv").read_text().splitlines()

    products = navcam_products(lines, sol=152)

    assert [p.file_stem for p in products] == [
        "HNM_0152_0680432615_348FDR_N0100001HELI03026_0000LUJ05"
    ]
    assert products[0].url_dir == (
        "https://pds-imaging.jpl.nasa.gov/data/mars2020/mars2020_helicam/data/sol/00152/ids/fdr/heli/"
    )
    assert len(navcam_products(lines, sol=133)) == 12
    # The archive's version 7.0 is the file name's "07".
    assert navcam_products(lines, sol=133)[1].file_stem.endswith("LUJ07")


def test_a_label_gives_flight_altitude_and_clock():
    frame = read_label(LABEL.read_text())

    # Label: HELI_G_FRAME_10, the drone at z = -12.278 m (z points down).
    assert frame.flight == 10
    assert frame.altitude_m == pytest.approx(12.278, abs=0.001)
    assert frame.sclk == pytest.approx(680432615.348227)
    assert frame.lines == 480 and frame.samples == 640


def _frame(i: int, altitude: float) -> NavcamFrame:
    return NavcamFrame(
        file_stem=f"F{i:02d}", flight=10, altitude_m=altitude, sclk=float(i), lines=480, samples=640
    )


def test_choose_frames_spreads_picks_over_the_cruise_part_of_the_flight():
    # 2 low frames at take-off, 10 at cruise height, 2 low at landing.
    frames = [_frame(i, alt) for i, alt in enumerate([1, 6] + [12.0] * 10 + [6, 1])]

    picked = choose_frames(frames, count=4, min_altitude_ratio=0.8)

    assert [f.file_stem for f in picked] == ["F02", "F05", "F08", "F11"]


def test_choose_frames_takes_all_cruise_frames_when_there_are_few():
    frames = [_frame(i, alt) for i, alt in enumerate([1, 12, 12, 1])]

    picked = choose_frames(frames, count=10, min_altitude_ratio=0.8)

    assert [f.file_stem for f in picked] == ["F01", "F02"]


def test_choose_frames_takes_the_middle_cruise_frame_when_asked_for_one():
    frames = [_frame(i, alt) for i, alt in enumerate([1, 12, 12, 12, 1])]

    picked = choose_frames(frames, count=1, min_altitude_ratio=0.8)

    assert [f.file_stem for f in picked] == ["F02"]


def test_choose_frames_refuses_an_empty_flight():
    with pytest.raises(ValueError, match="no Navcam frames"):
        choose_frames([], count=10, min_altitude_ratio=0.8)
