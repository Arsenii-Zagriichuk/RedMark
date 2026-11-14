"""Layers 1 to 3 at Gale: the base photo map and slope (P2-02), and the class-map layers
for walkability and science (P2-03, at the end of this file), as layer files.

Each layer is a folder holding layer.json and its image tiles, laid out by the
layer contract (contracts/schemas/layer.json): at max_zoom one pixel is
resolution_m, each lower zoom halves the resolution, and tile (x, y) counts
from the north-west corner of the bounds. Zoom 0 is one tile holding the whole
layer. A tile reaching past the bounds is transparent there; a tile wholly past
them is not written, as the app never asks for it. Going down a zoom, the photo
averages its pixels and the slope averages its degrees before they are coloured,
so slope tiles at every zoom are coloured only in legend colours.

The slope itself, in degrees on the terrain's own grid, is also written as a
GeoTIFF for the route engine (route/layers.py).
"""

import json
import math
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import rasterio
import rasterio.windows
from PIL import Image
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject

from contracts.models.layer import LayerMeta
from prep.common import Bounds, written_atomically
from prep.gale.pack import slope_degrees
from prep.gale.science import HIGHLIGHT_PERCENTILE, MINERAL_INDICES, mineral_classes
from prep.gale.walkability import SAND_MAX_TI

# 250 px tiles divide the 4 km walk area exactly at both 25 cm (64 tiles) and 1 m (16).
TILE_SIZE = 250
BASE_RES_M = 0.25
SLOPE_RES_M = 1.0

# Upper edge in degrees and colour of each slope band. The edges at 15° and 20°
# are the route's two slope limits (the Artemis 20° and the team's 15° option).
SLOPE_BANDS: list[tuple[float, str]] = [
    (5.0, "#1a9850"),
    (10.0, "#91cf60"),
    (15.0, "#fee08b"),
    (20.0, "#fc8d59"),
    (30.0, "#d73027"),
    (math.inf, "#67001f"),
]


def slope_raster(terrain: Path, out: Path) -> Path:
    """Slope in degrees from a terrain GeoTIFF, on the terrain's own grid.

    A cell is unknown (NaN) where its own height or a neighbour's is missing.
    """
    with rasterio.open(terrain) as src:
        heights = src.read(1, masked=True).astype(np.float64).filled(np.nan)
        res_x, res_y = src.res
        if not math.isclose(res_x, res_y):
            raise ValueError(f"{terrain}: slope needs square pixels, got {src.res}")
        profile = src.profile
    slope = slope_degrees(heights, res_x)
    slope[np.isnan(heights)] = np.nan
    profile.update(
        driver="GTiff",
        dtype="float32",
        nodata=np.nan,
        compress="deflate",
        predictor=3,
        tiled=True,
        blockxsize=256,
        blockysize=256,
    )
    with written_atomically(out) as part, rasterio.open(part, "w", **profile) as dst:
        dst.write(slope.astype(np.float32), 1)
    return out


def build_base_layer(photo: Path, bounds: Bounds, folder: Path, source: dict) -> dict:
    """The photo map cut to `bounds` at 25 cm, as grey JPEG tiles."""
    image = _on_layer_grid(photo, bounds, BASE_RES_M, Resampling.nearest)
    grey = np.nan_to_num(image, nan=0).astype(np.uint8)
    zooms = write_tiles(photo_levels(Image.fromarray(grey, "L")), folder, "jpg")
    return _write_meta(
        folder,
        name="base",
        title="HiRISE photo map",
        units="",
        res=BASE_RES_M,
        bounds=bounds,
        zooms=zooms,
        ext="jpg",
        legend=[{"label": "HiRISE photo, 25 cm", "color": "#808080"}],
        source=source,
    )


def build_slope_layer(slope: Path, bounds: Bounds, folder: Path, source: dict) -> dict:
    """The slope raster on a 1 m grid over `bounds`, coloured by band, as PNG tiles."""
    degrees = _on_layer_grid(slope, bounds, SLOPE_RES_M, Resampling.bilinear)
    levels = [Image.fromarray(slope_colours(d), "RGBA") for d in slope_levels(degrees)]
    zooms = write_tiles(levels, folder, "png")
    return _write_meta(
        folder,
        name="slope",
        title="Slope",
        units="°",
        res=SLOPE_RES_M,
        bounds=bounds,
        zooms=zooms,
        ext="png",
        legend=slope_legend(),
        source=source,
    )


def slope_legend() -> list[dict]:
    legend, low = [], 0.0
    for high, colour in SLOPE_BANDS:
        label = f"{low:g}–{high:g}°" if math.isfinite(high) else f"{low:g}° and steeper"
        legend.append({"label": label, "color": colour, "value": low})
        low = high
    return legend


def slope_colours(degrees: np.ndarray) -> np.ndarray:
    """RGBA for each cell: its band's colour, transparent where the slope is unknown."""
    rgba = np.zeros((*degrees.shape, 4), dtype=np.uint8)
    known = np.isfinite(degrees)
    band = np.searchsorted([high for high, _ in SLOPE_BANDS], np.where(known, degrees, 0), "right")
    for index, (_, colour) in enumerate(SLOPE_BANDS):
        rgba[known & (band == index)] = (*_rgb(colour), 255)
    return rgba


def write_tiles(levels: list[Image.Image], folder: Path, ext: str) -> tuple[int, int]:
    """Write a zoom pyramid, levels[z] being the layer at zoom z (pixel 0, 0 at the
    north-west corner), under folder/tiles/{z}/{x}/{y}.<ext>. Returns (min_zoom, max_zoom)."""
    for z, level in enumerate(levels):
        for x, y, tile in _cut(level, TILE_SIZE):
            path = folder / "tiles" / str(z) / str(x) / f"{y}.{ext}"
            path.parent.mkdir(parents=True, exist_ok=True)
            tile.save(path, quality=90) if ext == "jpg" else tile.save(path, optimize=True)
    return 0, len(levels) - 1


def max_zoom(width: int, height: int, tile_size: int) -> int:
    """The zoom at which full-resolution pixels fill the tiles: 2**max_zoom tiles
    of `tile_size` span the longer side."""
    return math.ceil(math.log2(math.ceil(max(width, height) / tile_size)))


def photo_levels(image: Image.Image) -> list[Image.Image]:
    """The photo at every zoom, 0 first: each zoom down averages 2 x 2 pixels."""
    levels = [image]
    for _ in range(max_zoom(image.width, image.height, TILE_SIZE)):
        levels.append(levels[-1].reduce(2))
    return levels[::-1]


def slope_levels(degrees: np.ndarray) -> list[np.ndarray]:
    """The slope at every zoom, 0 first: each pixel is the mean of the known 1 m
    cells it covers, taken before any colour is given, so every zoom shows legend
    colours and the bands stay put as the map zooms. Each zoom down adds up the sums
    and counts of known cells, so a block with gaps weighs only the cells it knows.
    A pixel is unknown only where every cell it covers is."""
    known = np.isfinite(degrees)
    total = np.where(known, degrees, 0).astype(np.float64)
    count = known.astype(np.int64)
    levels = [degrees]
    for _ in range(max_zoom(degrees.shape[1], degrees.shape[0], TILE_SIZE)):
        total, count = _sum_2x2(total), _sum_2x2(count)
        with np.errstate(invalid="ignore", divide="ignore"):
            levels.append(np.where(count > 0, total / count, np.nan).astype(degrees.dtype))
    return levels[::-1]


def _sum_2x2(values: np.ndarray) -> np.ndarray:
    """Each 2 x 2 block added up; an odd last row or column counts as zeros past it."""
    rows, cols = values.shape
    even = np.zeros((rows + rows % 2, cols + cols % 2), dtype=values.dtype)
    even[:rows, :cols] = values
    return even[0::2, 0::2] + even[0::2, 1::2] + even[1::2, 0::2] + even[1::2, 1::2]


def _cut(image: Image.Image, tile_size: int) -> Iterator[tuple[int, int, Image.Image]]:
    """Every (x, y, tile) of one zoom; a tile reaching past the image is transparent there."""
    for x in range(math.ceil(image.width / tile_size)):
        for y in range(math.ceil(image.height / tile_size)):
            box = (x * tile_size, y * tile_size, (x + 1) * tile_size, (y + 1) * tile_size)
            yield x, y, image.crop(box)


def _on_layer_grid(path: Path, bounds: Bounds, res: float, resampling: Resampling) -> np.ndarray:
    """Band 1 of `path` resampled onto the `res` grid whose corner is the bounds'
    north-west corner. Missing data comes back as NaN.

    GDAL's bilinear resampling fills a hole from the pixels round it, so for any
    resampling but nearest, a pixel that draws on a missing one is missing too:
    an unknown slope is never shown as a guessed one.
    """
    min_x, min_y, max_x, max_y = bounds
    width, height = round((max_x - min_x) / res), round((max_y - min_y) / res)
    if not (math.isclose(width * res, max_x - min_x) and math.isclose(height * res, max_y - min_y)):
        raise ValueError(f"bounds {bounds} are not a whole number of {res} m pixels")
    out = np.full((height, width), np.nan, dtype=np.float32)
    grid = {"dst_transform": from_origin(min_x, max_y, res, res), "resampling": resampling}
    with rasterio.open(path) as src:
        if resampling == Resampling.nearest:
            band = rasterio.band(src, 1)
            reproject(band, out, src_nodata=src.nodata, dst_nodata=np.nan, dst_crs=src.crs, **grid)
            return out
        values = src.read(1, masked=True).astype(np.float32).filled(np.nan)
        source = {"src_transform": src.transform, "src_crs": src.crs, "dst_crs": src.crs}
    missing = np.isnan(values).astype(np.float32)
    reproject(values, out, src_nodata=np.nan, dst_nodata=np.nan, **source, **grid)
    touched = np.ones_like(out)
    reproject(missing, touched, **source, **grid)
    out[touched > 0] = np.nan
    return out


def _write_meta(
    folder, *, name, title, units, res, bounds, zooms, ext, legend, source, group=1
) -> dict:
    min_x, min_y, max_x, max_y = bounds
    meta = {
        "name": name,
        "title": title,
        "group": group,
        "units": units,
        "resolution_m": res,
        "bounds": {"min_x": min_x, "min_y": min_y, "max_x": max_x, "max_y": max_y},
        "tiles": {
            "path": f"tiles/{{z}}/{{x}}/{{y}}.{ext}",
            "tile_size": TILE_SIZE,
            "min_zoom": zooms[0],
            "max_zoom": zooms[1],
        },
        "legend": legend,
        "source": source if isinstance(source, list) else [source],
    }
    LayerMeta.model_validate(meta)
    with written_atomically(folder / "layer.json") as part:
        part.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    return meta


def _rgb(colour: str) -> tuple[int, int, int]:
    return int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16)


# ---- layers 2 and 3 (P2-03) ---------------------------------------------------------
#
# Each is a class map: a small code per pixel, 0 for nothing shown, each other code a
# legend row. Going down a zoom a pixel keeps the highest code it covers, so a thin
# ridge or a lone chemistry point never averages away, and every tile shows only
# legend colours. Layers made straight from a coarse source (thermal inertia at 100 m,
# CRISM at 18 m) keep that source's own pixels: their bounds are the walk area grown
# out to whole source pixels, so nothing is resampled.

SAND_COLOUR = "#e0a43a"
RIDGE_COLOUR = "#e8341c"
# Highest code first wins where a pixel is in two classes.
MINERAL_COLOURS = {
    "hydrated": "#4f8fd6",
    "clay": "#2ca25f",
    "monohydrated_sulfate": "#f2b134",
    "polyhydrated_sulfate": "#d6408f",
}
CHEMISTRY_RES_M = 1.0
CHEMISTRY_DOT_M = 3.0  # radius of each APXS point
DRILL_DOT_M = 6.0  # radius of each drill site
# SO3 (wt%) bands for APXS points: in the walk area the median is about 14 wt%.
SO3_BANDS: list[tuple[float, str]] = [
    (10.0, "#fcc5c0"),
    (15.0, "#f768a1"),
    (20.0, "#ae017e"),
    (math.inf, "#49006a"),
]
DRILL_COLOUR = "#00d8ff"


def build_sand_layer(sand: Path, walk: Bounds, folder: Path, source: dict) -> dict:
    """Loose sand from the sand raster, on its own 100 m pixels."""
    values, bounds, res = _on_own_grid(sand, walk)
    classes = (values == 1).astype(np.uint8)
    legend = [(1, f"Loose sand (THEMIS thermal inertia below {SAND_MAX_TI})", SAND_COLOUR)]
    return build_class_layer(
        classes, bounds, res, folder, name="sand", title="Loose sand", group=2,
        units="", legend=legend, source=source,
    )  # fmt: skip


def build_ridges_layer(ridges: Path, walk: Bounds, folder: Path, source: dict) -> dict:
    """Boxwork ridges from the ridge raster, on its own 50 cm pixels."""
    values, bounds, res = _on_own_grid(ridges, walk)
    classes = (values == 1).astype(np.uint8)
    legend = [(1, "Boxwork ridge (mapped in boxwork zones only)", RIDGE_COLOUR)]
    return build_class_layer(
        classes, bounds, res, folder, name="ridges", title="Boxwork ridges", group=2,
        units="", legend=legend, source=source,
    )  # fmt: skip


def build_minerals_layer(crism: Path, walk: Bounds, folder: Path, source: dict) -> dict:
    """CRISM mineral highlights on the CRISM cube's own 18 m pixels."""
    with rasterio.open(crism) as src:
        names = list(src.descriptions)
    bands = {
        name: _on_own_grid(crism, walk, band=names.index(name) + 1)[0]
        for name in (index for index, _, _ in MINERAL_INDICES)
    }
    _, bounds, res = _on_own_grid(crism, walk)
    classes = mineral_classes(bands)
    legend = [
        (code, f"{label} ({index} in the walk area's top {100 - HIGHLIGHT_PERCENTILE:g}%)",
         MINERAL_COLOURS[key])
        for code, (index, key, label) in enumerate(MINERAL_INDICES, start=1)
    ]  # fmt: skip
    return build_class_layer(
        classes, bounds, res, folder, name="minerals", title="Mineral highlights (CRISM)",
        group=3, units="", legend=legend, source=source,
    )  # fmt: skip


def build_chemistry_layer(points: list[dict], walk: Bounds, folder: Path, source: dict) -> dict:
    """APXS points along Curiosity's track as dots coloured by SO3, drill sites on top.

    Each point is {"x", "y", "so3" (wt%), "drill" (bool)}."""
    min_x, min_y, max_x, max_y = walk
    res = CHEMISTRY_RES_M
    shape = (round((max_y - min_y) / res), round((max_x - min_x) / res))
    rows, cols = np.mgrid[0 : shape[0], 0 : shape[1]]
    x, y = min_x + (cols + 0.5) * res, max_y - (rows + 0.5) * res
    classes = np.zeros(shape, dtype=np.uint8)
    drill_code = len(SO3_BANDS) + 1
    edges = [high for high, _ in SO3_BANDS]
    for p in sorted(points, key=lambda p: p["drill"]):
        radius = DRILL_DOT_M if p["drill"] else CHEMISTRY_DOT_M
        code = drill_code if p["drill"] else int(np.searchsorted(edges, p["so3"], "right")) + 1
        dot = (x - p["x"]) ** 2 + (y - p["y"]) ** 2 <= radius**2
        classes[dot] = np.maximum(classes[dot], code)
    legend, low = [], 0.0
    for code, (high, colour) in enumerate(SO3_BANDS, start=1):
        label = (
            f"APXS SO3 {low:g}–{high:g} wt%"
            if math.isfinite(high)
            else f"APXS SO3 {low:g} wt% and over"
        )
        legend.append((code, label, colour))
        low = high
    legend.append((drill_code, "Drill site (APXS on drill tailings)", DRILL_COLOUR))
    return build_class_layer(
        classes, walk, res, folder, name="chemistry", title="Curiosity chemistry (APXS)",
        group=3, units="SO3 wt%", legend=legend, source=source,
    )  # fmt: skip


def build_class_layer(
    classes: np.ndarray, bounds: Bounds, res: float, folder: Path, *, name: str, title: str,
    group: int, units: str, legend: list[tuple[int, str, str]], source: dict,
) -> dict:  # fmt: skip
    """A class map (row 0 at the north edge of `bounds`) as PNG tiles plus layer.json.
    `legend` is (code, label, colour) per class; code 0 is transparent."""
    colours = {code: colour for code, _, colour in legend}
    levels = [
        Image.fromarray(_class_colours(level, colours), "RGBA") for level in class_levels(classes)
    ]
    zooms = write_tiles(levels, folder, "png")
    return _write_meta(
        folder, name=name, title=title, units=units, res=res, bounds=bounds, zooms=zooms,
        ext="png", legend=[{"label": label, "color": colour} for _, label, colour in legend],
        source=source, group=group,
    )  # fmt: skip


def class_levels(classes: np.ndarray) -> list[np.ndarray]:
    """The class map at every zoom, 0 first: each pixel keeps the highest code it covers."""
    levels = [classes]
    for _ in range(max_zoom(classes.shape[1], classes.shape[0], TILE_SIZE)):
        level = levels[-1]
        rows, cols = level.shape
        even = np.zeros((rows + rows % 2, cols + cols % 2), dtype=level.dtype)
        even[:rows, :cols] = level
        levels.append(
            np.maximum.reduce(
                [even[0::2, 0::2], even[0::2, 1::2], even[1::2, 0::2], even[1::2, 1::2]]
            )
        )
    return levels[::-1]


def snapped_bounds(transform, bounds: Bounds) -> Bounds:
    """`bounds` grown out to the nearest whole pixels of a north-up grid."""
    res_x, res_y = transform.a, -transform.e
    min_x, min_y, max_x, max_y = bounds
    col0 = math.floor(round((min_x - transform.c) / res_x, 6))
    col1 = math.ceil(round((max_x - transform.c) / res_x, 6))
    row0 = math.floor(round((transform.f - max_y) / res_y, 6))
    row1 = math.ceil(round((transform.f - min_y) / res_y, 6))
    return (
        transform.c + col0 * res_x,
        transform.f - row1 * res_y,
        transform.c + col1 * res_x,
        transform.f - row0 * res_y,
    )


def _on_own_grid(path: Path, bounds: Bounds, band: int = 1) -> tuple[np.ndarray, Bounds, float]:
    """One band of `path` over `bounds` grown to its whole pixels, unresampled.
    Missing data and pixels past the file come back as NaN."""
    with rasterio.open(path) as src:
        res_x, res_y = src.res
        if not math.isclose(res_x, res_y):
            raise ValueError(f"{path}: needs square pixels, got {src.res}")
        snapped = snapped_bounds(src.transform, bounds)
        window = (
            rasterio.windows.from_bounds(*snapped, src.transform).round_offsets().round_lengths()
        )
        values = src.read(band, window=window, boundless=True, masked=True)
    values = values.astype(np.float64).filled(np.nan)
    return values, snapped, res_x


def _class_colours(classes: np.ndarray, colours: dict[int, str]) -> np.ndarray:
    rgba = np.zeros((*classes.shape, 4), dtype=np.uint8)
    for code, colour in colours.items():
        rgba[classes == code] = (*_rgb(colour), 255)
    return rgba
