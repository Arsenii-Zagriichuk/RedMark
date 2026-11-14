"""A horizon fix's provenance names every file the fix and its overlay read."""

from contracts.paths import REPO_ROOT
from locate.horizon.base_map import read_layer_image
from locate.horizon.fix import GRID, PLACES, fix_provenance
from locate.horizon.tests.test_horizon_base_map import write_layer


def test_provenance_records_the_frames_grid_answer_key_site_config_and_base_map(tmp_path):
    for name in (GRID, PLACES, "navcam/A.LBL", "navcam/A.IMG"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(name)
    (tmp_path / "gale/layers/base").mkdir(parents=True)
    write_layer(tmp_path / "gale/layers/base")
    base_map = read_layer_image(tmp_path / "gale/layers/base", pixels_across=8)

    provenance = fix_provenance(
        [tmp_path / "navcam/A.LBL"],
        tmp_path,
        REPO_ROOT / "sites/gale.yaml",
        base_map,
        commit="0" * 40,
    )

    recorded = {item.path for item in provenance.inputs}
    tiles = {f"gale/layers/base/tiles/1/{x}/{y}.png" for x in range(2) for y in range(2)}
    assert recorded == {
        GRID,
        PLACES,
        "navcam/A.LBL",
        "navcam/A.IMG",
        "sites/gale.yaml",  # a repo file, recorded from the repo root
        "gale/layers/base/layer.json",
        *tiles,
    }
    assert all(len(item.sha256) == 64 for item in provenance.inputs)
