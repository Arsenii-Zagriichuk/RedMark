"""Layer 5 files: tiles and layer.json in the layer contract, and the score as a GeoTIFF."""

import numpy as np
import pytest
import rasterio
from PIL import Image

from contracts.models.layer import LayerMeta
from layers.location_quality.layer_files import LegendClass, write_geotiff, write_tile_layer
from layers.location_quality.visibility import Cells

PROJECTION = "+proj=eqc +lat_ts=0 +lon_0=0 +R=3396190 +units=m +no_defs"
# 300 rows by 600 columns of 1 m cells.
CELLS = Cells(left=1_000.0, top=-2_000.0, res=1.0, shape=(300, 600))


def test_a_tile_layer_is_in_the_layer_contract_with_a_full_pyramid(tmp_path):
    # Left half seen (1), right half not (0).
    values = np.zeros(CELLS.shape, np.float32)
    values[:, :300] = 1.0
    legend = [LegendClass("Seen", "#2a9d8f", 1.0), LegendClass("Not seen", "#264653", 0.0)]
    folder = tmp_path / "landmark_texoli"
    write_tile_layer(
        folder,
        values,
        CELLS,
        title="Texoli in view",
        units="seen",
        legend=legend,
        sources=[("MSL Gale DEM mosaic, 1 m, v3", "https://planetarymaps.usgs.gov/x.tif")],
    )
    meta = LayerMeta.model_validate_json((folder / "layer.json").read_text())
    assert meta.name == "landmark_texoli"
    assert meta.group == 5
    assert meta.resolution_m == 1.0
    assert (meta.bounds.min_x, meta.bounds.max_x) == (1_000.0, 1_600.0)
    assert (meta.bounds.min_y, meta.bounds.max_y) == (-2_300.0, -2_000.0)
    # 600 x 300 px at 1 m is 3 x 2 tiles of 256 px; 2 m is 300 x 150 px, 2 x 1
    # tiles; 4 m is 150 x 75 px, one tile, the coarsest zoom.
    assert (meta.tiles.min_zoom, meta.tiles.max_zoom, meta.tiles.tile_size) == (0, 2, 256)
    for zoom, across, down in [(2, 3, 2), (1, 2, 1), (0, 1, 1)]:
        found = sorted(
            p.relative_to(folder).as_posix() for p in (folder / "tiles" / str(zoom)).rglob("*.png")
        )
        expected = sorted(
            meta.tiles.path.format(z=zoom, x=x, y=y) for x in range(across) for y in range(down)
        )
        assert found == expected
    # At full resolution, a pixel on the left is the "Seen" colour, one on the
    # right "Not seen", and past the right edge of the cells (x > 600 px) clear.
    tile = np.asarray(Image.open(folder / "tiles/2/0/0.png").convert("RGBA"))
    assert tuple(tile[10, 10]) == (0x2A, 0x9D, 0x8F, 255)
    right = np.asarray(Image.open(folder / "tiles/2/2/0.png").convert("RGBA"))
    assert tuple(right[10, 10]) == (0x26, 0x46, 0x53, 255)  # x = 522 px
    assert right[10, 100, 3] == 0  # x = 612 px, outside the cells
    assert [(e.label, e.color, e.value) for e in meta.legend] == [
        ("Seen", "#2a9d8f", 1.0),
        ("Not seen", "#264653", 0.0),
    ]


def test_the_score_geotiff_holds_the_values_in_the_site_projection(tmp_path):
    values = np.full(CELLS.shape, 0.25, np.float32)
    values[0, 0] = 1.0
    path = tmp_path / "rasters" / "location_quality.tif"
    write_geotiff(path, values, CELLS, PROJECTION)
    with rasterio.open(path) as src:
        assert src.read(1)[0, 0] == pytest.approx(1.0)
        assert src.read(1)[299, 599] == pytest.approx(0.25)
        assert src.transform.c == 1_000.0 and src.transform.f == -2_000.0
        assert src.res == (1.0, 1.0)
        assert src.crs.to_proj4().startswith("+proj=eqc")
