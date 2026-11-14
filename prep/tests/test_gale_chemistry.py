"""Seam: Curiosity's chemistry points land where the rover stood.

APXS tables give a sol and target but no position; each measurement's source
file names carry the rover's site and drive, and PLACES gives the position of
every site and drive. Expected positions are copied from PLACES.
"""

from pathlib import Path

import pytest

from prep.gale.pack import apxs_points, rover_poses

FIXTURES = Path(__file__).parent / "fixtures"
# The tables differ: the newer one names its last column (the source files).
APXS = [
    FIXTURES / "apxs_concentrations_4489_4612_excerpt.csv",
    FIXTURES / "apxs_concentrations_4710_4843_excerpt.csv",
]
INTERP = FIXTURES / "places_localized_interp_excerpt.csv"
EVERYWHERE = (-1e9, -1e9, 1e9, 1e9)


def test_every_rover_drive_has_one_position_and_site_rows_are_left_out():
    poses = rover_poses(INTERP)

    # PLACES rows: SITE 114, rover 114/2214, 114/2292, 121/762, and 121/0 twice
    # (poses 0 and 2, the same spot).
    assert set(poses) == {(114, 2214), (114, 2292), (121, 0), (121, 762)}
    assert poses[(121, 0)] == (8143317.832, -285084.215)


def test_an_apxs_measurement_sits_at_the_rover_position_of_its_site_and_drive():
    points = apxs_points(APXS, rover_poses(INTERP), EVERYWHERE)

    # Chuckwalla_DRT, sol 4500: source files ...ESC4500 114 2292..., and
    # PLACES puts site 114 drive 2292 at (8143745.073, -284139.645).
    chuckwalla = next(p for p in points if p["target"] == "Chuckwalla_DRT")
    assert (chuckwalla["site"], chuckwalla["drive"]) == (114, 2292)
    assert (chuckwalla["x"], chuckwalla["y"]) == (8143745.073, -284139.645)
    # Concentrations as published: SO3 14.91 wt%, FeO 18.03 wt%, Br 1338 ppm.
    assert chuckwalla["SO3"] == pytest.approx(14.91)
    assert chuckwalla["FeO"] == pytest.approx(18.03)
    assert chuckwalla["Br"] == pytest.approx(1338)
    assert chuckwalla["Br_err"] == pytest.approx(45)
    assert "data_products" not in chuckwalla


def test_points_come_in_sol_order_from_every_table():
    points = apxs_points(APXS, rover_poses(INTERP), EVERYWHERE)

    assert [(p["sol"], p["target"]) for p in points] == [
        (4498, "Los_Osos_DRT"),
        (4500, "Chuckwalla_DRT"),
        (4842, "Challapata_DRT"),
    ]


def test_the_table_that_names_its_source_file_column_is_read_the_same_way():
    points = apxs_points(APXS, rover_poses(INTERP), EVERYWHERE)

    # Challapata_DRT, sol 4842: ...ESC4842 121 0762..., at PLACES 121/762.
    challapata = points[-1]
    assert (challapata["site"], challapata["drive"]) == (121, 762)
    assert (challapata["x"], challapata["y"]) == (8143262.049, -285136.262)
    assert set(challapata) == set(points[0])


def test_points_outside_the_bounds_are_left_out():
    # Only Challapata (site 121 drive 762, at 8143262.049, -285136.262) is south of -285000.
    bounds = (8143000.0, -285500.0, 8144000.0, -285000.0)

    points = apxs_points(APXS, rover_poses(INTERP), bounds)

    assert [p["target"] for p in points] == ["Challapata_DRT"]


def test_a_measurement_with_no_position_in_places_is_refused():
    with pytest.raises(ValueError, match="114/2292"):
        apxs_points(APXS, {(114, 2214): (0.0, 0.0), (121, 762): (0.0, 0.0)}, EVERYWHERE)
