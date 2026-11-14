"""Reading a layer's tiles into one map image. Expected values are worked by hand."""

import json

import matplotlib.pyplot as plt
import numpy as np
import pytest

from locate.horizon.base_map import read_layer_image

# 2 x 2 tiles of 4 px at 10 m a pixel at zoom 1 (20 m a pixel at zoom 0):
# 80 m square, north-west corner at (1000, 2080).
LAYER = {
    "name": "base",
    "title": "Made-up base map",
    "group": 1,
    "units": "",
    "resolution_m": 10.0,
    "bounds": {"min_x": 1000, "min_y": 2000, "max_x": 1080, "max_y": 2080},
    "tiles": {"path": "tiles/{z}/{x}/{y}.png", "tile_size": 4, "min_zoom": 0, "max_zoom": 1},
    "legend": [{"label": "Photo", "color": "#808080"}],
    "source": [{"name": "Made up", "url": "https://example.org"}],
}


def write_layer(folder):
    (folder / "layer.json").write_text(json.dumps(LAYER))
    for x in range(2):
        for y in range(2):
            tile = np.full((4, 4, 3), (x * 0.5, y * 0.5, 1.0), np.float32)
            path = folder / "tiles" / "1" / str(x) / f"{y}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            plt.imsave(path, tile)
    zoom0 = folder / "tiles" / "0" / "0" / "0.png"
    zoom0.parent.mkdir(parents=True, exist_ok=True)
    plt.imsave(zoom0, np.zeros((4, 4, 3), np.float32))


def test_tiles_are_laid_out_from_the_north_west_corner(tmp_path):
    write_layer(tmp_path)
    layer = read_layer_image(tmp_path, pixels_across=8)
    assert layer.title == "Made-up base map"
    assert layer.extent == (1000, 1080, 2000, 2080)  # left, right, bottom, top
    assert layer.image.shape[:2] == (8, 8)
    # Tile x counts east, tile y counts south from the north-west corner.
    assert layer.image[0, 0, :3] == pytest.approx([0.0, 0.0, 1.0], abs=0.01)
    assert layer.image[0, 7, :3] == pytest.approx([0.5, 0.0, 1.0], abs=0.01)
    assert layer.image[7, 0, :3] == pytest.approx([0.0, 0.5, 1.0], abs=0.01)


def test_the_coarsest_zoom_that_keeps_enough_pixels_is_read(tmp_path):
    # 4 px across is enough for the whole map at zoom 0, so the one black
    # zoom-0 tile is read instead of the four zoom-1 tiles.
    write_layer(tmp_path)
    layer = read_layer_image(tmp_path, pixels_across=4)
    assert layer.image.shape[:2] == (4, 4)
    assert layer.image[..., :3].max() == 0.0


def test_the_files_read_are_listed_for_provenance(tmp_path):
    write_layer(tmp_path)
    layer = read_layer_image(tmp_path, pixels_across=8)
    tiles = [tmp_path / "tiles" / "1" / str(x) / f"{y}.png" for x in range(2) for y in range(2)]
    assert sorted(layer.files) == sorted([tmp_path / "layer.json", *tiles])
