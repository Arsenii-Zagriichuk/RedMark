"""The Gale pack's overlay images: each source on the base map, to check by eye."""

import json
import math
from pathlib import Path

import matplotlib
import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import Resampling

from prep.common import Bounds
from prep.gale.rasters import read_window

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle, Patch, Rectangle  # noqa: E402

OVERLAY_PX = 2000  # long side of the downsampled base map in each overlay
ZOOM_HALF_M = 300  # half-width of the full-detail zoom panels


def photo_map(root, crops, walk, habitat, base_camp, positions, check, folder) -> None:
    image, extent = _read_small(root / crops["photo_map"]["path"])
    fig, (wide, zoom) = plt.subplots(1, 2, figsize=(22, 11), gridspec_kw={"wspace": 0.08})
    for ax in (wide, zoom):
        _show_gray(ax, image, extent)
        ax.plot([p["x"] for p in positions], [p["y"] for p in positions], "-", c="red", lw=1)
        ax.plot([p["x"] for p in positions], [p["y"] for p in positions], "o", c="red", ms=2.5)
        ax.plot(*habitat, "*", c="cyan", ms=16, mec="black", label="habitat")
        ax.plot(*base_camp, "^", c="yellow", ms=10, mec="black", label="base camp")
    _walk_area_patches(wide, walk, habitat)
    for p in positions[:: max(1, len(positions) // 12)]:
        wide.annotate(
            f"sol {p['sol']}",
            (p["x"], p["y"]),
            color="red",
            fontsize=8,
            xytext=(4, 4),
            textcoords="offset points",
        )
    wide.plot([], [], "-o", c="red", ms=2.5, label="Curiosity (PLACES)")
    wide.legend(loc="lower left")
    wide.set_title("Base map: walk area, habitat, base camp and Curiosity's positions")
    # Full detail round Curiosity's stop nearest the habitat.
    nearest = min(positions, key=lambda p: np.hypot(p["x"] - habitat[0], p["y"] - habitat[1]))
    cx, cy = nearest["x"], nearest["y"]
    detail, detail_extent = read_window(
        root / crops["photo_map"]["path"],
        (cx - ZOOM_HALF_M, cy - ZOOM_HALF_M, cx + ZOOM_HALF_M, cy + ZOOM_HALF_M),
    )
    _show_gray(zoom, detail, detail_extent)
    zoom.plot([p["x"] for p in positions], [p["y"] for p in positions], "-o", c="red", ms=3, lw=1)
    zoom.set_xlim(detail_extent[0], detail_extent[1])
    zoom.set_ylim(detail_extent[2], detail_extent[3])
    photo, dem = check["photo_map"], check["terrain"]
    zoom.set_title(
        f"Curiosity's drive nearest the habitat, full detail. PLACES grid vs ours: "
        f"photo map {photo['offset_px']} px "
        f"({photo['off_grid_m']} m off grid), terrain {dem['offset_px']} px "
        f"({dem['off_grid_m']} m off grid)",
        fontsize=9,
    )
    _save(fig, folder / "photo-map.png")


def terrain(root, crops, walk, habitat, folder) -> None:
    image, extent = _read_small(root / crops["photo_map"]["path"])
    heights, h_extent = _read_small(root / crops["terrain"]["path"], float_data=True)
    fig, (wide, zoom) = plt.subplots(1, 2, figsize=(22, 11), gridspec_kw={"wspace": 0.08})
    _show_gray(wide, image, extent)
    res = (h_extent[1] - h_extent[0]) / heights.shape[1]
    wide.imshow(_hillshade(heights, res), cmap="gray", alpha=0.5, extent=h_extent)
    _walk_area_patches(wide, walk, habitat)
    wide.set_title("1 m terrain hillshade (50%) on the base map")
    # Full detail at the habitat, where the mesa edge gives a sharp line to match.
    x, y = habitat
    box = (x - ZOOM_HALF_M, y - ZOOM_HALF_M, x + ZOOM_HALF_M, y + ZOOM_HALF_M)
    photo, p_extent = read_window(root / crops["photo_map"]["path"], box)
    shade, s_extent = read_window(root / crops["terrain"]["path"], box, float_data=True)
    _show_gray(zoom, photo, p_extent)
    zoom.imshow(_hillshade(shade, 1.0), cmap="gray", alpha=0.5, extent=s_extent)
    zoom.set_xlim(p_extent[0], p_extent[1])
    zoom.set_ylim(p_extent[2], p_extent[3])
    zoom.plot(*habitat, "*", c="cyan", ms=16, mec="black")
    zoom.set_title("At the habitat, 1 m: hillshade (50%) on the photo; edges should not double")
    _save(fig, folder / "terrain.png")


def thermal_inertia(root, crops, walk, habitat, offset, folder) -> None:
    image, extent = _read_small(root / crops["photo_map"]["path"])
    with rasterio.open(root / crops["thermal_inertia"]["path"]) as src:
        ti = src.read(1, masked=True).astype(np.float32).filled(np.nan)
        b = src.bounds
    ti_extent = (b.left, b.right, b.bottom, b.top)
    fig, (alone, blended) = plt.subplots(1, 2, figsize=(22, 11), gridspec_kw={"wspace": 0.12})
    low, high = np.nanpercentile(ti, [2, 98])
    _show_gray(alone, image, extent)
    shown = alone.imshow(
        ti, cmap="inferno", vmin=low, vmax=high, extent=ti_extent, interpolation="nearest"
    )
    _show_gray(blended, image, extent)
    blended.imshow(
        ti,
        cmap="inferno",
        vmin=low,
        vmax=high,
        extent=ti_extent,
        alpha=0.45,
        interpolation="nearest",
    )
    for ax in (alone, blended):
        _walk_area_patches(ax, walk, habitat)
    fig.colorbar(shown, ax=[alone, blended], shrink=0.7, label="thermal inertia (J m⁻² K⁻¹ s⁻½)")
    alone.set_title("THEMIS thermal inertia, 100 m")
    photo, slope = offset["photo_brightness"], offset["slope"]
    blended.set_title(
        f"Thermal inertia (45%) on the base map, not shifted. Best-matching move: "
        f"{photo['best_move_m']} m (r {photo['r_unmoved']} to {photo['r_best']}) by brightness, "
        f"{slope['best_move_m']} m (r {slope['r_unmoved']} to {slope['r_best']}) by slope",
        fontsize=9,
    )
    _save(fig, folder / "thermal-inertia.png")


def crism(root, crops, walk, habitat, offset, folder) -> None:
    """R770 on the base map: the whole crop moved, and at the habitat before and after."""
    image, extent = _read_small(root / crops["photo_map"]["path"])
    with rasterio.open(root / crops["crism"]["path"]) as src:
        r770 = src.read(src.descriptions.index("R770") + 1, masked=True)
        b = src.bounds
    r770 = r770.astype(np.float32).filled(np.nan)
    r770[np.abs(r770) > 1e3] = np.nan
    moved = (b.left, b.right, b.bottom, b.top)
    east, north = offset["move_m"] if offset["applied"] else (0.0, 0.0)
    unmoved = (b.left - east, b.right - east, b.bottom - north, b.top - north)
    low, high = np.nanpercentile(r770, [2, 98])
    fig, axes = plt.subplots(1, 3, figsize=(30, 10.5), gridspec_kw={"wspace": 0.12})
    x, y = habitat
    box = (x - 2 * ZOOM_HALF_M, y - 2 * ZOOM_HALF_M, x + 2 * ZOOM_HALF_M, y + 2 * ZOOM_HALF_M)
    detail, d_extent = read_window(root / crops["photo_map"]["path"], box)
    for ax, layer_extent, title in (
        (axes[0], moved, f"CRISM R770 (45%) on the base map, moved {[east, north]} m"),
        (axes[1], unmoved, "At the habitat, as published (ENVI header)"),
        (axes[2], moved, f"At the habitat, moved {[east, north]} m: bright and dark should match"),
    ):
        if ax is axes[0]:
            _show_gray(ax, image, extent)
            _walk_area_patches(ax, walk, habitat)
        else:
            _show_gray(ax, detail, d_extent)
            ax.set_xlim(d_extent[0], d_extent[1])
            ax.set_ylim(d_extent[2], d_extent[3])
        ax.imshow(
            r770,
            cmap="viridis",
            vmin=low,
            vmax=high,
            extent=layer_extent,
            alpha=0.45,
            interpolation="nearest",
        )
        ax.plot(*habitat, "*", c="cyan", ms=16, mec="black")
        ax.set_title(title, fontsize=10)
    fig.suptitle(
        f"CRISM FRT0000B6F1, 18 m. Best move by correlation with the photo map: "
        f"{offset['move_m']} m, r {offset['r_unmoved']} unmoved to {offset['r_best']} "
        f"({'applied' if offset['applied'] else 'not applied'})",
        fontsize=12,
    )
    _save(fig, folder / "crism.png")


def chemistry(root, crops, walk, habitat, positions, chemistry, folder) -> None:
    """Curiosity's APXS measurements on the base map, coloured by sulphate (SO3)."""
    image, extent = _read_small(root / crops["photo_map"]["path"])
    fig, (wide, zoom) = plt.subplots(1, 2, figsize=(22, 11), gridspec_kw={"wspace": 0.12})
    xs, ys = [p["x"] for p in chemistry], [p["y"] for p in chemistry]
    so3 = [p["SO3"] for p in chemistry]
    low, high = np.percentile(so3, [2, 98])  # so one high reading does not wash out the rest
    pad = 60.0
    box = (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)
    detail, d_extent = read_window(root / crops["photo_map"]["path"], box)
    _show_gray(wide, image, extent)
    _walk_area_patches(wide, walk, habitat)
    _show_gray(zoom, detail, d_extent)
    for ax in (wide, zoom):
        ax.plot([p["x"] for p in positions], [p["y"] for p in positions], "-", c="red", lw=1)
        shown = ax.scatter(
            xs, ys, c=so3, cmap="plasma", vmin=low, vmax=high, s=40, edgecolors="black", zorder=3
        )
        ax.plot(*habitat, "*", c="cyan", ms=16, mec="black")
    zoom.set_xlim(d_extent[0], d_extent[1])
    zoom.set_ylim(d_extent[2], d_extent[3])
    for p in chemistry[:: max(1, len(chemistry) // 15)]:
        zoom.annotate(
            f"{p['target']} (sol {p['sol']})",
            (p["x"], p["y"]),
            fontsize=7,
            color="white",
            xytext=(5, 5),
            textcoords="offset points",
        )
    fig.colorbar(shown, ax=[wide, zoom], shrink=0.7, extend="both", label="SO3 (wt%)")
    wide.set_title(
        f"{len(chemistry)} APXS measurements (sols {chemistry[0]['sol']} to "
        f"{chemistry[-1]['sol']}) at the rover's PLACES position, on the base map"
    )
    zoom.set_title("Along the track: each point within about 2 m of its target (arm reach)")
    _save(fig, folder / "chemistry.png")


def slope_layer(root, photo, layer, walk, habitat, folder) -> None:
    """The slope layer's own tiles on the photo map: whole walk area and the habitat."""
    meta = json.loads((layer / "layer.json").read_text())
    image, extent = _read_small(photo)
    fig, (wide, zoom) = plt.subplots(1, 2, figsize=(22, 11), gridspec_kw={"wspace": 0.08})
    _show_gray(wide, image, extent)
    colours, c_extent = _mosaic(layer, 2)
    wide.imshow(colours, alpha=0.55, extent=c_extent)
    _walk_area_patches(wide, walk, habitat)
    wide.set_xlim(walk[0], walk[2])
    wide.set_ylim(walk[1], walk[3])
    wide.legend(
        handles=[Patch(color=e["color"], label=e["label"]) for e in meta["legend"]],
        loc="lower left",
        fontsize=9,
    )
    wide.set_title("Slope layer tiles (zoom 2, 4 m) at 55% on the base map")
    x, y = habitat
    box = (x - ZOOM_HALF_M, y - ZOOM_HALF_M, x + ZOOM_HALF_M, y + ZOOM_HALF_M)
    detail, p_extent = read_window(photo, box)
    _show_gray(zoom, detail, p_extent)
    colours, c_extent = _mosaic(layer, meta["tiles"]["max_zoom"], box)
    zoom.imshow(colours, alpha=0.45, extent=c_extent)
    zoom.set_xlim(p_extent[0], p_extent[1])
    zoom.set_ylim(p_extent[2], p_extent[3])
    zoom.plot(*habitat, "*", c="cyan", ms=16, mec="black")
    zoom.set_title("At the habitat, 1 m tiles at 45%: steep bands follow ridge and mesa edges")
    _save(fig, folder / "slope.png")


def base_tiles(photo, layer, walk, habitat, positions, folder) -> None:
    """The base layer's tiles placed only by layer.json, beside the crop placed by its
    own GeoTIFF transform, with Curiosity's positions on both."""
    meta = json.loads((layer / "layer.json").read_text())
    fig, (wide, tiles, crop) = plt.subplots(1, 3, figsize=(30, 10.5), gridspec_kw={"wspace": 0.1})
    overview, o_extent = _mosaic(layer, 3)
    _show_gray(wide, overview, o_extent)
    step = meta["tiles"]["tile_size"] * meta["resolution_m"] * 2 ** (meta["tiles"]["max_zoom"] - 3)
    for edge in np.arange(walk[0], walk[2] + 1, step):
        wide.axvline(edge, c="orange", lw=0.6)
    for edge in np.arange(walk[1], walk[3] + 1, step):
        wide.axhline(edge, c="orange", lw=0.6)
    xs, ys = [p[0] for p in positions], [p[1] for p in positions]
    wide.plot(xs, ys, "o", c="red", ms=2.5, label="Curiosity (PLACES)")
    wide.plot(*habitat, "*", c="cyan", ms=16, mec="black", label="habitat")
    wide.legend(loc="lower left", fontsize=9)
    wide.set_title("Base layer tiles at zoom 3 (2 m), placed by layer.json; orange: tile edges")
    # Full detail round Curiosity's last stop in the walk area, on the boxwork.
    x, y = positions[-1]
    box = (x - 60, y - 60, x + 60, y + 60)
    detail, t_extent = _mosaic(layer, meta["tiles"]["max_zoom"], box)
    pixels, p_extent = read_window(photo, box)
    for ax, image, extent, what in (
        (tiles, detail, t_extent, "base layer tiles at 25 cm, placed by layer.json"),
        (crop, pixels, p_extent, "the photo-map crop, placed by its GeoTIFF transform"),
    ):
        _show_gray(ax, image, extent)
        ax.plot(xs, ys, "o", c="red", ms=5)
        ax.set_xlim(box[0], box[2])
        ax.set_ylim(box[1], box[3])
        ax.set_title(f"{what}; red: Curiosity (PLACES)")
    _save(fig, folder / "base-tiles.png")


def _mosaic(layer: Path, zoom: int, box: Bounds | None = None) -> tuple[np.ndarray, tuple]:
    """A layer's tiles at `zoom` pasted together by the layer contract's rule (pixel
    size doubles each zoom down; tile x, y from the north-west corner of the bounds),
    only those overlapping `box` if given. Returns the image and its extent."""
    meta = json.loads((layer / "layer.json").read_text())
    b, t = meta["bounds"], meta["tiles"]
    size = t["tile_size"]
    tile_m = size * meta["resolution_m"] * 2 ** (t["max_zoom"] - zoom)
    columns = math.ceil((b["max_x"] - b["min_x"]) / tile_m)
    rows = math.ceil((b["max_y"] - b["min_y"]) / tile_m)
    x0, y0, x1, y1 = 0, 0, columns - 1, rows - 1
    if box is not None:
        x0 = max(0, math.floor((box[0] - b["min_x"]) / tile_m))
        x1 = min(columns - 1, math.floor((box[2] - b["min_x"]) / tile_m))
        y0 = max(0, math.floor((b["max_y"] - box[3]) / tile_m))
        y1 = min(rows - 1, math.floor((b["max_y"] - box[1]) / tile_m))
    pasted = None
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            path = t["path"].replace("{z}", str(zoom)).replace("{x}", str(x)).replace("{y}", str(y))
            tile = np.asarray(Image.open(layer / path))
            if pasted is None:
                shape = ((y1 - y0 + 1) * size, (x1 - x0 + 1) * size, *tile.shape[2:])
                pasted = np.zeros(shape, dtype=tile.dtype)
            row, col = (y - y0) * size, (x - x0) * size
            pasted[row : row + size, col : col + size] = tile
    west, north = b["min_x"] + x0 * tile_m, b["max_y"] - y0 * tile_m
    extent = (west, west + (x1 - x0 + 1) * tile_m, north - (y1 - y0 + 1) * tile_m, north)
    return pasted, extent


def _read_small(path: Path, float_data: bool = False) -> tuple[np.ndarray, tuple]:
    with rasterio.open(path) as src:
        scale = max(src.width, src.height) / OVERLAY_PX
        shape = (round(src.height / scale), round(src.width / scale))
        data = src.read(1, out_shape=shape, resampling=Resampling.average, masked=True)
        b = src.bounds
    data = data.astype(np.float32).filled(np.nan) if float_data else data.filled(0)
    return data, (b.left, b.right, b.bottom, b.top)


def _show_gray(ax, image: np.ndarray, extent: tuple) -> None:
    valid = image[image > 0]
    low, high = np.percentile(valid, [1, 99]) if valid.size else (0, 255)
    ax.imshow(image, cmap="gray", vmin=low, vmax=high, extent=extent)
    ax.ticklabel_format(useOffset=False, style="plain")
    ax.tick_params(labelsize=7)
    ax.set_xlabel("easting (m)")
    ax.set_ylabel("northing (m)")


def _walk_area_patches(ax, walk: Bounds, habitat: tuple[float, float]) -> None:
    min_x, min_y, max_x, max_y = walk
    ax.add_patch(
        Rectangle(
            (min_x, min_y),
            max_x - min_x,
            max_y - min_y,
            fill=False,
            ec="cyan",
            lw=1.5,
            label="walk area",
        )
    )
    ax.add_patch(Circle(habitat, (max_x - min_x) / 2, fill=False, ec="cyan", lw=1, ls="--"))


def _hillshade(heights: np.ndarray, res: float) -> np.ndarray:
    """Light from the north-west, 45° up."""
    dy, dx = np.gradient(np.nan_to_num(heights, nan=np.nanmedian(heights)), res)
    slope = np.arctan(np.hypot(dx, dy))
    aspect = np.arctan2(-dx, dy)
    azimuth, altitude = np.radians(315.0), np.radians(45.0)
    shade = np.sin(altitude) * np.cos(slope) + np.cos(altitude) * np.sin(slope) * np.cos(
        azimuth - aspect
    )
    return np.clip(shade, 0, 1)


def _save(fig, path: Path) -> None:
    fig.savefig(path, dpi=80, bbox_inches="tight")
    plt.close(fig)
