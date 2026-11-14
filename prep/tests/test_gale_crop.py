"""Seam: crop a Gale source to the walk area.

Every Gale source is already in the site projection, so a crop is a window on
the source's own pixel grid, never resampled. A pixel with known coordinates
lands where it should, and the crop covers the asked bounds.
"""

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_origin

from prep.gale.crop import crop_on_source_grid

SITE_PROJ = "+proj=eqc +lat_ts=0 +lon_0=0 +R=3396190 +units=m +no_defs"
MARKER = 200.0


def _source(path: Path, crs: str = SITE_PROJ) -> Path:
    """50 x 40 heights at 1 m, with the left edge half a metre off the whole
    metre like the real Gale terrain, and one marked pixel at row 10, col 20."""
    heights = np.zeros((40, 50), dtype=np.float32)
    heights[10, 20] = MARKER
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=50,
        height=40,
        count=1,
        dtype="float32",
        crs=CRS.from_proj4(crs),
        transform=from_origin(1000.5, 2000.0, 1.0, 1.0),
        nodata=-32767.0,
    ) as dst:
        dst.write(heights, 1)
    return path


def test_a_known_pixel_lands_at_its_place_in_the_crop(tmp_path: Path):
    source = _source(tmp_path / "source.tif")
    out = tmp_path / "crop.tif"

    crop_on_source_grid(source, (1010.0, 1980.0, 1030.0, 1995.0), out, SITE_PROJ, "test source")

    # The marked pixel's centre is x = 1000.5 + 20.5 = 1021.0,
    # y = 2000 - 10.5 = 1989.5. The crop starts at source col 9 (left edge
    # 1009.5) and row 5 (top edge 1995), so the pixel is at row 5, col 11.
    with rasterio.open(out) as crop:
        heights = crop.read(1)
        assert heights[5, 11] == MARKER
        assert np.count_nonzero(heights == MARKER) == 1
        assert crop.xy(5, 11) == (1021.0, 1989.5)
        assert crop.crs == CRS.from_proj4(SITE_PROJ)
        assert crop.nodata == -32767.0


def test_the_crop_covers_the_bounds_snapped_out_to_whole_source_pixels(tmp_path: Path):
    source = _source(tmp_path / "source.tif")
    out = tmp_path / "crop.tif"

    covered = crop_on_source_grid(
        source, (1010.0, 1980.0, 1030.0, 1995.0), out, SITE_PROJ, "test source"
    )

    # West and east snap out to the source's half-metre pixel edges.
    assert covered == (1009.5, 1980.0, 1030.5, 1995.0)
    with rasterio.open(out) as crop:
        assert tuple(crop.bounds) == covered
        assert crop.res == (1.0, 1.0)


def test_a_source_in_another_projection_is_refused(tmp_path: Path):
    source = _source(tmp_path / "source.tif", crs="+proj=eqc +lat_ts=18.4663 +R=3396190")

    with pytest.raises(ValueError, match="projection"):
        crop_on_source_grid(
            source, (1010.0, 1980.0, 1030.0, 1995.0), tmp_path / "c.tif", SITE_PROJ, "test source"
        )


def test_bounds_past_the_edge_of_the_source_are_refused(tmp_path: Path):
    source = _source(tmp_path / "source.tif")

    with pytest.raises(ValueError, match="outside"):
        crop_on_source_grid(
            source, (990.0, 1980.0, 1030.0, 1995.0), tmp_path / "c.tif", SITE_PROJ, "test source"
        )
    assert not (tmp_path / "c.tif").exists()


def test_a_moved_crop_puts_a_known_pixel_at_its_moved_place(tmp_path: Path):
    # A source mislocated by 3 m west and 2 m north: moving it 3 m east and
    # 2 m south puts the marked pixel's centre at (1024.0, 1987.5).
    source = _source(tmp_path / "source.tif")
    out = tmp_path / "crop.tif"

    covered = crop_on_source_grid(
        source,
        (1010.0, 1980.0, 1030.0, 1995.0),
        out,
        SITE_PROJ,
        "test source",
        move_m=(3.0, -2.0),
    )

    with rasterio.open(out) as crop:
        row, col = crop.index(1024.0, 1987.5)
        assert crop.read(1)[row, col] == MARKER
        assert crop.xy(row, col) == (1024.0, 1987.5)
    # Still the asked bounds, overshooting by under a pixel a side.
    assert covered == (1009.5, 1980.0, 1030.5, 1995.0)


def test_every_band_and_its_name_is_kept(tmp_path: Path):
    source = tmp_path / "cube.tif"
    with rasterio.open(
        source,
        "w",
        driver="GTiff",
        width=10,
        height=10,
        count=2,
        dtype="float32",
        crs=CRS.from_proj4(SITE_PROJ),
        transform=from_origin(0.0, 10.0, 1.0, 1.0),
    ) as dst:
        dst.write(np.full((2, 10, 10), [[[1.0]], [[2.0]]], dtype=np.float32))
        dst.descriptions = ("R770", "BD1900R2")
    out = tmp_path / "crop.tif"

    crop_on_source_grid(source, (2.0, 2.0, 6.0, 6.0), out, SITE_PROJ, "cube")

    with rasterio.open(out) as crop:
        assert crop.count == 2
        assert crop.descriptions == ("R770", "BD1900R2")
        assert crop.read(2).min() == 2.0
