"""Write layer 5 for the app and the route.

The app reads map layers through the layer contract: a folder with layer.json
and PNG tiles, which the service serves from $REDMARK_DATA/<site>/layers/. At
the finest zoom one pixel is one cell; each lower zoom halves the resolution,
down to the zoom where the whole layer fits one tile. Each cell takes the
colour of the legend class whose value is nearest its own; cells with no value
and the margin past the cells' edge stay clear.

The route reads rasters, so the combined score also goes out as a one-band
GeoTIFF in the site projection (route/README.md, "Layer files the route needs").
"""

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.transform import from_origin

from contracts.models.layer import LayerMeta
from layers.location_quality.visibility import Cells

GROUP = 5
TILE_SIZE = 256
TILE_PATH = "tiles/{z}/{x}/{y}.png"


@dataclass(frozen=True)
class LegendClass:
    label: str
    color: str
    """Hex colour, #rrggbb."""
    value: float


def write_tile_layer(
    folder: Path,
    values: np.ndarray,
    cells: Cells,
    *,
    title: str,
    units: str,
    legend: list[LegendClass],
    sources: list[tuple[str, str]],
) -> LayerMeta:
    """Write layer.json and the tiles for one layer; the folder name is the layer name."""
    rgba = _colour(values, legend)
    rows, cols = values.shape
    max_zoom = max(0, math.ceil(math.log2(max(rows, cols) / TILE_SIZE)))
    for zoom in range(max_zoom, -1, -1):
        _write_tiles(folder, rgba, zoom)
        rgba = _halve(rgba)
    meta = LayerMeta.model_validate(
        {
            "name": folder.name,
            "title": title,
            "group": GROUP,
            "units": units,
            "resolution_m": cells.res,
            "bounds": {
                "min_x": cells.left,
                "min_y": cells.bottom,
                "max_x": cells.right,
                "max_y": cells.top,
            },
            "tiles": {
                "path": TILE_PATH,
                "tile_size": TILE_SIZE,
                "min_zoom": 0,
                "max_zoom": max_zoom,
            },
            "legend": [{"label": c.label, "color": c.color, "value": c.value} for c in legend],
            "source": [{"name": name, "url": url} for name, url in sources],
        }
    )
    (folder / "layer.json").write_text(
        json.dumps(meta.model_dump(mode="json", exclude_none=True), indent=2) + "\n"
    )
    return meta


def write_geotiff(path: Path, values: np.ndarray, cells: Cells, projection: str) -> None:
    """One float32 band in the site projection; NaN where there is no value."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=values.shape[0],
        width=values.shape[1],
        count=1,
        dtype="float32",
        crs=projection,
        transform=from_origin(cells.left, cells.top, cells.res, cells.res),
        nodata=np.nan,
        compress="deflate",
    ) as dst:
        dst.write(values.astype(np.float32), 1)


def _colour(values: np.ndarray, legend: list[LegendClass]) -> np.ndarray:
    """RGBA (float, 0 to 1) of the nearest legend class for each value; clear where NaN."""
    class_values = np.array([c.value for c in legend])
    colours = np.array([[int(c.color[i : i + 2], 16) / 255 for i in (1, 3, 5)] for c in legend])
    nearest = np.abs(np.nan_to_num(values, nan=np.inf)[..., None] - class_values).argmin(axis=-1)
    rgba = np.zeros((*values.shape, 4), np.float32)
    rgba[..., :3] = colours[nearest]
    rgba[..., 3] = ~np.isnan(values)
    return rgba


def _write_tiles(folder: Path, rgba: np.ndarray, zoom: int) -> None:
    rows, cols = rgba.shape[:2]
    for tx in range(math.ceil(cols / TILE_SIZE)):
        for ty in range(math.ceil(rows / TILE_SIZE)):
            tile = np.zeros((TILE_SIZE, TILE_SIZE, 4), np.float32)
            part = rgba[
                ty * TILE_SIZE : (ty + 1) * TILE_SIZE, tx * TILE_SIZE : (tx + 1) * TILE_SIZE
            ]
            tile[: part.shape[0], : part.shape[1]] = part
            path = folder / TILE_PATH.format(z=zoom, x=tx, y=ty)
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(np.rint(tile * 255).astype(np.uint8), "RGBA").save(path)


def _halve(rgba: np.ndarray) -> np.ndarray:
    """Half the resolution: each pixel averages a 2 x 2 block, colours weighted
    by how opaque they are, so clear pixels don't darken the edges."""
    rows, cols = rgba.shape[:2]
    padded = np.zeros((rows + rows % 2, cols + cols % 2, 4), np.float32)
    padded[:rows, :cols] = rgba
    blocks = padded.reshape(padded.shape[0] // 2, 2, padded.shape[1] // 2, 2, 4)
    alpha = blocks[..., 3].sum(axis=(1, 3))
    colour = (blocks[..., :3] * blocks[..., 3:]).sum(axis=(1, 3))
    out = np.zeros((*alpha.shape, 4), np.float32)
    out[..., :3] = colour / np.maximum(alpha, 1e-9)[..., None]
    out[..., 3] = alpha / 4
    return out
