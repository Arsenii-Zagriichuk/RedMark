"""Seam: Curiosity's chemistry points land where the rover stood.

APXS tables give a sol and target but no position. PLACES gives the rover's
position after every drive, so a measurement sits where the rover's last
drive before its sol ended. (Where a table's source-file names can be trusted,
their site and drive give the same position for every row; in the sol 3193 to
4133 table they are scrambled.) Expected positions are copied from PLACES.
"""

from pathlib import Path

import pytest

from prep.gale.pack import (
    apxs_points,
    apxs_tables_for,
    check_apxs_placement,
    rover_sols_inside,
    rover_track,
)

FIXTURES = Path(__file__).parent / "fixtures"
# The tables differ: the newer one names its last column (the source files).
APXS = [
    FIXTURES / "apxs_concentrations_3193_4133_excerpt.csv",
    FIXTURES / "apxs_concentrations_4489_4612_excerpt.csv",
    FIXTURES / "apxs_concentrations_4710_4843_excerpt.csv",
]
INTERP = FIXTURES / "places_localized_interp_excerpt.csv"
EVERYWHERE = (-1e9, -1e9, 1e9, 1e9)


def test_the_track_holds_every_rover_pose_in_order_and_no_site_rows():
    track = rover_track(INTERP)

    # PLACES rows: SITE 114 (left out), and rover poses on sols 3192, 3899,
    # 4496, 4498, 4834 (twice: poses 0 and 2) and 4841.
    assert [p["sol"] for p in track] == [3192, 3899, 4496, 4498, 4834, 4834, 4841]
    assert (track[0]["site"], track[0]["drive"]) == (90, 232)
    assert (track[0]["x"], track[0]["y"]) == (8144444.860, -281105.747)


def test_an_apxs_measurement_sits_at_the_rover_position_of_its_site_and_drive():
    points = apxs_points(APXS, rover_track(INTERP), EVERYWHERE)

    # Chuckwalla_DRT, sol 4500: the rover's last drive before it ended on sol
    # 4498 at site 114 drive 2292, (8143745.073, -284139.645); its source
    # files name the same site and drive (...ESC4500 114 2292...).
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
    points = apxs_points(APXS, rover_track(INTERP), EVERYWHERE)

    assert [(p["sol"], p["target"]) for p in points] == [
        (3194, "Bregout"),
        (4498, "Los_Osos_DRT"),
        (4500, "Chuckwalla_DRT"),
        (4842, "Challapata_DRT"),
    ]


def test_the_table_that_names_its_source_file_column_is_read_the_same_way():
    points = apxs_points(APXS, rover_track(INTERP), EVERYWHERE)

    # Challapata_DRT, sol 4842: the last drive before it ended on sol 4841 at
    # 121/762, as its files say (...ESC4842 121 0762...).
    challapata = points[-1]
    assert (challapata["site"], challapata["drive"]) == (121, 762)
    assert (challapata["x"], challapata["y"]) == (8143262.049, -285136.262)
    assert set(challapata) == set(points[0])


def test_points_outside_the_bounds_are_left_out():
    # Only Challapata (site 121 drive 762, at 8143262.049, -285136.262) is south of -285000.
    bounds = (8143000.0, -285500.0, 8144000.0, -285000.0)

    points = apxs_points(APXS, rover_track(INTERP), bounds)

    assert [p["target"] for p in points] == ["Challapata_DRT"]


def test_a_measurement_whose_files_name_another_sol_is_placed_by_its_own_sol():
    # Bregout, sol 3194, in the scrambled table: its files name sol 3900 at
    # site 102 drive 2428. The rover's last drive before sol 3194 ended on sol
    # 3192 at site 90 drive 232, (8144444.860, -281105.747).
    bregout = apxs_points(APXS, rover_track(INTERP), EVERYWHERE)[0]

    assert bregout["target"] == "Bregout"
    assert (bregout["site"], bregout["drive"]) == (90, 232)
    assert (bregout["x"], bregout["y"]) == (8144444.860, -281105.747)


def test_a_measurement_before_the_first_rover_pose_is_refused():
    track = rover_track(INTERP)[1:]  # nothing before sol 3899

    with pytest.raises(ValueError, match="Bregout"):
        apxs_points(APXS, track, EVERYWHERE)


def test_the_sols_curiosity_spent_inside_the_bounds_come_from_places():
    # Inside: 114/2214 (sol 4496), 114/2292 (4498), 121/0 (4834), 121/762 (4841).
    bounds = (8143000.0, -285500.0, 8144000.0, -284000.0)

    assert rover_sols_inside(INTERP, bounds) == (4496, 4841)


def test_every_table_overlapping_the_sols_is_read():
    tables = [
        "msl_apxs_concentrations_3069_3192.csv",
        "msl_apxs_concentrations_3193_4133.csv",
        "msl_apxs_concentrations_4134_4257.csv",
        "msl_apxs_concentrations_4710_4843.csv",
    ]

    # Sols 3843 to 4200 touch the second and third tables only.
    assert apxs_tables_for(tables, (3843, 4200)) == tables[1:3]


def test_blank_rows_and_a_notes_column_are_skipped(tmp_path):
    lines = (FIXTURES / "apxs_concentrations_4710_4843_excerpt.csv").read_text().splitlines()
    header = lines[0].replace(",data_products", ",Notes,data_products")
    row = lines[1].rsplit(",", 1)
    table = tmp_path / "with_notes.csv"
    table.write_text(f"{header}\n{row[0]},a note,{row[1]}\n\n")

    points = apxs_points([table], rover_track(INTERP), EVERYWHERE)

    assert [p["target"] for p in points] == ["Challapata_DRT"]
    assert "Notes" not in points[0]


def test_placing_by_sol_is_checked_against_trustworthy_file_names():
    # Los_Osos, Chuckwalla and Challapata name their own sol in their files,
    # and their site and drive match the pose placed by sol. Bregout's files
    # name sol 3900, so it is left out of the check.
    check = check_apxs_placement(APXS, rover_track(INTERP))

    assert check == {"rows_checked": 3, "same_pose": 3, "files_name_another_sol": 1}
