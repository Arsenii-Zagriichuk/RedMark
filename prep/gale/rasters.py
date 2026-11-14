"""Read the Gale crops: averaged to coarser pixels, or a window at full detail."""

from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import Window

from prep.common import Bounds
from prep.gale.pack import PixelGrid


def read_at(path: Path, res_m: float) -> tuple[np.ndarray, PixelGrid]:
    """A crop averaged to `res_m` pixels, with NaN for no data, and its grid.

    `res_m` must be a whole number of the crop's pixels; only whole blocks are
    read, so each averaged pixel is exactly `res_m` wide.
    """
    with rasterio.open(path) as src:
        factor = round(res_m / src.res[0])
        shape = (src.height // factor, src.width // factor)
        window = Window(0, 0, shape[1] * factor, shape[0] * factor)
        data = src.read(
            1, window=window, out_shape=shape, resampling=Resampling.average, masked=True
        )
        grid = PixelGrid(src.bounds.left, src.bounds.top, factor * src.res[0])
    data = data.astype(np.float64)
    if src.dtypes[0] == "uint8":  # the photo map's 0 is no data
        data = np.ma.masked_equal(data, 0)
    return data.filled(np.nan), grid


def read_window(path: Path, box: Bounds, float_data: bool = False) -> tuple[np.ndarray, tuple]:
    """The crop's pixels inside `box` at full detail, and their extent (left, right, bottom, top).

    A box past the crop's edge is cut at the edge, and the extent says so.
    """
    with rasterio.open(path) as src:
        window = rasterio.windows.from_bounds(*box, transform=src.transform)
        window = window.round_offsets().round_lengths()
        window = window.intersection(Window(0, 0, src.width, src.height))
        data = src.read(1, window=window, masked=True)
        b = rasterio.windows.bounds(window, src.transform)
    data = data.astype(np.float32).filled(np.nan) if float_data else data.filled(0)
    return data, (b[0], b[2], b[1], b[3])
