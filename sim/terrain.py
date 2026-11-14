from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager

import numpy as np
import rasterio
from rasterio.vrt import WarpedVRT
from rasterio.windows import Window, from_bounds

from contracts.models.site import SiteConfig
from contracts.paths import data_root

HAZARD_SLOPE_DEG = 20.0


@contextmanager
def terrain_at(
    site: SiteConfig, *, require_files: bool = True
) -> Iterator[Callable[[np.ndarray, float], str]]:
    with ExitStack() as stack:
        layers = {}
        for name in ("slope", "ridges"):
            if name not in site.files:
                continue
            path = data_root() / site.files[name]
            if not path.is_file():
                if require_files:
                    raise FileNotFoundError(
                        f"{name} layer {path} named in the {site.site} site config"
                    )
                layers[name] = None
                continue
            source = stack.enter_context(rasterio.open(path))
            layers[name] = stack.enter_context(
                WarpedVRT(
                    source,
                    src_crs=source.crs or site.projection,
                    crs=site.projection,
                    add_alpha=True,
                )
            )

        def at(position: np.ndarray, radius_m: float) -> str:
            terrain = "open"
            for name, layer in layers.items():
                if layer is None:
                    return "hazard"
                values = _values_in_circle(layer, *position, radius_m)
                if not values.size or np.any(np.ma.getmaskarray(values)):
                    return "hazard"
                if name == "slope" and np.any(values > HAZARD_SLOPE_DEG):
                    return "hazard"
                if name == "ridges" and np.any(values > 0):
                    terrain = "boxwork"
            return terrain

        yield at


def _values_in_circle(layer, x: float, y: float, radius_m: float) -> np.ma.MaskedArray:
    bounds = layer.bounds
    if (
        x - radius_m < bounds.left
        or x + radius_m > bounds.right
        or y - radius_m < bounds.bottom
        or y + radius_m > bounds.top
    ):
        return np.ma.masked_all(1)
    window = from_bounds(x - radius_m, y - radius_m, x + radius_m, y + radius_m, layer.transform)
    col, row = int(np.floor(window.col_off)), int(np.floor(window.row_off))
    width = int(np.ceil(window.col_off + window.width)) - col
    height = int(np.ceil(window.row_off + window.height)) - row
    band, alpha = layer.read((1, layer.count), window=Window(col, row, width, height))
    values = np.ma.array(band, mask=alpha == 0)
    transform = layer.transform
    left = transform.c + (col + np.arange(width)) * transform.a
    top = transform.f + (row + np.arange(height)) * transform.e
    dx = np.maximum(np.maximum(left - x, x - left - transform.a), 0)
    dy = np.maximum(np.maximum(y - top, top + transform.e - y), 0)
    return np.ma.masked_invalid(values[np.hypot(dx[None, :], dy[:, None]) <= radius_m])
