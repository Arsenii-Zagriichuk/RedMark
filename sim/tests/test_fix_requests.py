import numpy as np
import pytest
from rasterio.transform import from_origin

from sim.engine import simulate
from sim.tests.helpers import walk, write_summary, write_terrain


def test_a_fix_is_requested_once_when_the_circle_passes_five_metres_in_boxwork(
    tmp_path, monkeypatch
):
    sites = write_terrain(tmp_path, monkeypatch, ridges=np.ones((2, 22)))

    run = simulate(walk([(0, 0), (2000, 0)], radio_off=True), sites_root=sites)

    requested = [s for s in run["steps"] if {"kind": "fix_requested"} in s["events"]]
    assert len(requested) == 1
    at = run["steps"].index(requested[0])
    assert run["steps"][at]["uncertainty_m"] > 5 >= run["steps"][at - 1]["uncertainty_m"]


def test_hazards_request_a_fix_at_three_metres_even_inside_boxwork(tmp_path, monkeypatch):
    sites = write_terrain(
        tmp_path, monkeypatch, slope=np.full((2, 22), 21), ridges=np.ones((2, 22))
    )

    run = simulate(walk([(0, 0), (2000, 0)], radio_off=True), sites_root=sites)

    requested = [s for s in run["steps"] if {"kind": "fix_requested"} in s["events"]]
    assert len(requested) == 1
    at = run["steps"].index(requested[0])
    assert run["steps"][at]["uncertainty_m"] > 3 >= run["steps"][at - 1]["uncertainty_m"]


@pytest.mark.parametrize("layer", ["slope", "ridges"])
def test_unknown_terrain_uses_the_near_hazard_limit(tmp_path, monkeypatch, layer):
    sites = write_terrain(tmp_path, monkeypatch, **{layer: np.full((2, 22), -9999)})

    run = simulate(walk([(0, 0), (2000, 0)], radio_off=True), sites_root=sites)

    requested = [s for s in run["steps"] if {"kind": "fix_requested"} in s["events"]]
    assert len(requested) == 1
    at = run["steps"].index(requested[0])
    assert run["steps"][at]["uncertainty_m"] > 3 >= run["steps"][at - 1]["uncertainty_m"]


def test_entering_boxwork_requests_a_fix_when_the_circle_already_exceeds_five_metres(
    tmp_path, monkeypatch
):
    ridges = np.zeros((2, 22))
    ridges[:, 16:] = 1
    sites = write_terrain(tmp_path, monkeypatch, ridges=ridges)

    run = simulate(walk([(0, 0), (2000, 0)], radio_off=True), sites_root=sites)

    requested = [s for s in run["steps"] if {"kind": "fix_requested"} in s["events"]]
    assert len(requested) == 1
    at = run["steps"].index(requested[0])
    assert run["steps"][at - 1]["uncertainty_m"] > 5
    assert 1450 < requested[0]["true_position"]["x"] < 1550


def test_entering_a_hazard_escalates_an_outstanding_boxwork_fix_request(tmp_path, monkeypatch):
    slope = np.zeros((2, 22))
    slope[:, 17:] = 21
    sites = write_terrain(tmp_path, monkeypatch, slope=slope, ridges=np.ones((2, 22)))

    run = simulate(walk([(0, 0), (2000, 0)], radio_off=True), sites_root=sites)

    requested = [s for s in run["steps"] if {"kind": "fix_requested"} in s["events"]]
    assert len(requested) == 2
    assert requested[0]["uncertainty_m"] > 5
    assert 1550 < requested[1]["true_position"]["x"] < 1650
    assert requested[1]["uncertainty_m"] > requested[0]["uncertainty_m"]


def test_a_fix_request_rearms_after_a_fix_shrinks_the_circle(tmp_path, monkeypatch):
    sites = write_terrain(tmp_path, monkeypatch, slope=np.full((2, 22), 21))
    write_summary(tmp_path, 0.1)

    run = simulate(
        walk([(0, 0), (2000, 0)], fixes=[(1200, "horizon")], radio_off=True),
        results_root=tmp_path,
        sites_root=sites,
    )

    requested = [s for s in run["steps"] if {"kind": "fix_requested"} in s["events"]]
    assert len(requested) == 2
    assert requested[0]["t_s"] < 1200 < requested[1]["t_s"]


def test_walkable_slope_and_no_ridges_keep_the_ten_metre_open_ground_limit(tmp_path, monkeypatch):
    sites = write_terrain(
        tmp_path, monkeypatch, slope=np.full((2, 62), 20), ridges=np.zeros((2, 62))
    )

    run = simulate(walk([(0, 0), (6000, 0)], radio_off=True), sites_root=sites)

    requested = [s for s in run["steps"] if {"kind": "fix_requested"} in s["events"]]
    assert len(requested) == 1
    at = run["steps"].index(requested[0])
    assert run["steps"][at]["uncertainty_m"] > 10 >= run["steps"][at - 1]["uncertainty_m"]


def test_terrain_in_another_projection_is_sampled_in_the_site_map_frame(tmp_path, monkeypatch):
    sites = write_terrain(
        tmp_path,
        monkeypatch,
        raster_projection=(
            "+proj=eqc +lat_ts=0 +lon_0=0 +x_0=10000 +y_0=20000 +R=3396190 +units=m +no_defs"
        ),
        raster_transform=from_origin(9900, 20100, 100, 100),
        ridges=np.ones((2, 22)),
    )

    run = simulate(walk([(0, 0), (2000, 0)], radio_off=True), sites_root=sites)

    requested = [s for s in run["steps"] if {"kind": "fix_requested"} in s["events"]]
    assert len(requested) == 1
    at = run["steps"].index(requested[0])
    assert run["steps"][at]["uncertainty_m"] > 5 >= run["steps"][at - 1]["uncertainty_m"]


def test_an_explicit_hazard_distance_can_run_without_terrain_files(tmp_path, monkeypatch):
    sites = write_terrain(tmp_path, monkeypatch, ridges=np.ones((2, 22)))
    (tmp_path / "data" / "ridges.tif").unlink()

    run = simulate(
        walk([(0, 0), (2000, 0)], radio_off=True),
        hazard_distance_m=lambda x, y: float("inf"),
        sites_root=sites,
    )

    requested = [s for s in run["steps"] if {"kind": "fix_requested"} in s["events"]]
    assert len(requested) == 1
    at = run["steps"].index(requested[0])
    assert run["steps"][at]["uncertainty_m"] > 3 >= run["steps"][at - 1]["uncertainty_m"]


def test_a_missing_configured_layer_is_an_error_without_a_hazard_override(tmp_path, monkeypatch):
    sites = write_terrain(tmp_path, monkeypatch, ridges=np.ones((2, 22)))
    (tmp_path / "data" / "ridges.tif").unlink()

    with pytest.raises(FileNotFoundError, match="ridges"):
        simulate(walk([(0, 0), (2000, 0)], radio_off=True), sites_root=sites)
