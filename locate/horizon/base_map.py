"""Read a map layer (the layer contract) into one image for an overlay.

Overlays draw fixes on the site's base map, read through the layer contract,
so the real base map replaces the stub with no code change. The layer's title
goes on the overlay, so a stub base map is labelled as one.
"""

import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from contracts.models.layer import LayerMeta


@dataclass(frozen=True)
class LayerImage:
    title: str
    image: np.ndarray
    """RGBA, row 0 at the north edge; transparent where a tile is missing."""
    extent: tuple[float, float, float, float]
    """Left, right, bottom, top in map metres, as matplotlib's imshow takes it."""
    files: tuple[Path, ...]
    """Every file read: layer.json and the tiles, for provenance."""


def read_layer_image(folder: Path, *, pixels_across: int) -> LayerImage:
    """The layer at the coarsest zoom that still has pixels_across pixels
    across its wider side (or its finest zoom)."""
    layer = LayerMeta.model_validate_json((folder / "layer.json").read_text())
    bounds, tiles = layer.bounds, layer.tiles
    span_m = max(bounds.max_x - bounds.min_x, bounds.max_y - bounds.min_y)
    zoom = next(
        (
            z
            for z in range(tiles.min_zoom, tiles.max_zoom + 1)
            if span_m / _resolution(layer, z) >= pixels_across
        ),
        tiles.max_zoom,
    )
    tile_m = tiles.tile_size * _resolution(layer, zoom)
    across = math.ceil((bounds.max_x - bounds.min_x) / tile_m - 1e-9)
    down = math.ceil((bounds.max_y - bounds.min_y) / tile_m - 1e-9)
    size = tiles.tile_size
    image = np.zeros((down * size, across * size, 4), np.float32)
    files = [folder / "layer.json"]
    for x in range(across):
        for y in range(down):
            path = folder / tiles.path.format(z=zoom, x=x, y=y)
            if path.exists():
                tile = _rgba(plt.imread(path))
                image[y * size : (y + 1) * size, x * size : (x + 1) * size] = tile
                files.append(path)
    extent = (
        bounds.min_x,
        bounds.min_x + across * tile_m,
        bounds.max_y - down * tile_m,
        bounds.max_y,
    )
    return LayerImage(layer.title, image, extent, tuple(files))


def _resolution(layer: LayerMeta, zoom: int) -> float:
    return layer.resolution_m * 2 ** (layer.tiles.max_zoom - zoom)


def _rgba(tile: np.ndarray) -> np.ndarray:
    tile = tile.astype(np.float32)
    if tile.max() > 1.0:  # 8-bit JPEG tiles come back as 0 to 255
        tile = tile / 255.0
    if tile.ndim == 2:
        tile = np.repeat(tile[..., None], 3, axis=2)
    if tile.shape[2] == 3:
        tile = np.concatenate([tile, np.ones_like(tile[..., :1])], axis=2)
    return tile
