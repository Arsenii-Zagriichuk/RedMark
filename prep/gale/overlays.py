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
from matplotlib.patches import Circle, Patch, Polygon, Rectangle  # noqa: E402

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
    wide.set_title(
        "Slope tiles at zoom 2 (each 4 m pixel the mean of its 1 m slopes), 55% on the base map"
    )
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
    step = _tile_metres(meta, 3)
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
    tile_m = _tile_metres(meta, zoom)
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


def _tile_metres(meta: dict, zoom: int) -> float:
    """The ground span of one tile at `zoom`, by layer.json's rule: at max_zoom one
    pixel is resolution_m, and each zoom down doubles it."""
    t = meta["tiles"]
    return t["tile_size"] * meta["resolution_m"] * 2 ** (t["max_zoom"] - zoom)


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


# ---- layers 2 and 3 (P2-03) ---------------------------------------------------------

SAMPLE_HALF_M = 50  # half-width of each ridge sample area


def walkability(photo, layers, walk, habitat, zones, track, folder) -> Path:
    """Layer 2 placed by its own layer.json on the photo map: sand over the walk area,
    and the ridge map with its boxwork zones."""
    image, extent = _read_small(photo)
    sand_meta = json.loads((layers / "sand" / "layer.json").read_text())
    ridge_meta = json.loads((layers / "ridges" / "layer.json").read_text())
    fig, (wide, ridges) = plt.subplots(1, 2, figsize=(22, 11), gridspec_kw={"wspace": 0.08})
    _show_gray(wide, image, extent)
    colours, c_extent = _mosaic(layers / "sand", 0)
    wide.imshow(colours, alpha=0.5, extent=c_extent)
    _walk_area_patches(wide, walk, habitat)
    _track(wide, track)
    wide.plot(*habitat, "*", c="cyan", ms=16, mec="black")
    wide.set_xlim(walk[0], walk[2])
    wide.set_ylim(walk[1], walk[3])
    wide.legend(handles=_legend(sand_meta), loc="lower left", fontsize=9)
    wide.set_title(
        "Loose sand, 100 m THEMIS pixels from the sand layer's tiles, 50% on the base map"
    )
    # The boxwork zones together, with the ridge tiles at full resolution.
    xs = [p[0] for zone in zones for p in zone]
    ys = [p[1] for zone in zones for p in zone]
    box = (min(xs) - 50, min(ys) - 50, max(xs) + 50, max(ys) + 50)
    detail, p_extent = read_window(photo, box)
    _show_gray(ridges, detail[::4, ::4], p_extent)
    colours, c_extent = _mosaic(layers / "ridges", ridge_meta["tiles"]["max_zoom"] - 2, box)
    ridges.imshow(_masked(colours), extent=c_extent)
    for zone in zones:
        ridges.add_patch(Polygon(zone, closed=True, fill=False, ec="cyan", lw=1.5))
    _track(ridges, track)
    ridges.plot(*habitat, "*", c="cyan", ms=16, mec="black")
    ridges.set_xlim(box[0], box[2])
    ridges.set_ylim(box[1], box[3])
    ridges.legend(
        handles=[*_legend(ridge_meta), Patch(fill=False, ec="cyan", label="boxwork zone")],
        loc="lower left",
        fontsize=9,
    )
    ridges.set_title("Boxwork ridges (tiles at 2 m: a pixel is red if any 50 cm ridge pixel is)")
    out = folder / "walkability.png"
    _save(fig, out)
    return out


def ridge_samples(photo, layer, samples, targets, folder) -> Path:
    """Each sample area twice at full detail: the photo alone, then with the ridge
    tiles at 50 cm on it, to check the ridge map by eye. Science targets are marked."""
    meta = json.loads((layer / "layer.json").read_text())
    fig, axes = plt.subplots(len(samples), 2, figsize=(16, 8 * len(samples)))
    for (title, (x, y)), (bare, marked) in zip(samples, axes, strict=True):
        box = (x - SAMPLE_HALF_M, y - SAMPLE_HALF_M, x + SAMPLE_HALF_M, y + SAMPLE_HALF_M)
        detail, p_extent = read_window(photo, box)
        colours, c_extent = _mosaic(layer, meta["tiles"]["max_zoom"], box)
        for ax in (bare, marked):
            _show_gray(ax, detail, p_extent)
            ax.set_xlim(box[0], box[2])
            ax.set_ylim(box[1], box[3])
        marked.imshow(_masked(colours), alpha=0.6, extent=c_extent)
        for ax in (bare, marked):
            _targets(ax, targets, ms=14)
        bare.set_title(f"{title}: 25 cm photo")
        marked.set_title("with the ridge layer's 50 cm tiles at 60%")
    out = folder / "ridge-samples.png"
    _save(fig, out)
    return out


def science(photo, layers, walk, habitat, targets, drilled, track, folder) -> Path:
    """Layer 3 placed by its own layer.json on the photo map: CRISM mineral highlights
    over the walk area; Curiosity's chemistry and drill sites over the whole chemistry
    layer; then a close-up of the chemistry tiles at full detail round the drill sites
    inside the walk area."""
    image, extent = _read_small(photo)
    fig, (minerals, overview, zoom) = plt.subplots(
        1, 3, figsize=(33, 11), gridspec_kw={"wspace": 0.08}
    )
    meta = json.loads((layers / "minerals" / "layer.json").read_text())
    _show_gray(minerals, image, extent)
    colours, c_extent = _mosaic(layers / "minerals", meta["tiles"]["max_zoom"])
    minerals.imshow(_masked(colours), alpha=0.6, extent=c_extent)
    _walk_area_patches(minerals, walk, habitat)
    _track(minerals, track)
    minerals.plot(*habitat, "*", c="cyan", ms=16, mec="black")
    _targets(minerals, targets, ms=12)
    minerals.set_xlim(walk[0], walk[2])
    minerals.set_ylim(walk[1], walk[3])
    minerals.legend(handles=_legend(meta) + _target_handles(), loc="lower left", fontsize=8)
    minerals.set_title("CRISM highlights on its own 18 m pixels, 60% on the base map")

    meta = json.loads((layers / "chemistry" / "layer.json").read_text())
    b = meta["bounds"]
    whole = (b["min_x"], b["min_y"], b["max_x"], b["max_y"])
    inside = [
        d for d in drilled if whole[0] <= d["x"] <= whole[2] and whole[1] <= d["y"] <= whole[3]
    ]
    _show_gray(overview, image, extent)
    colours, c_extent = _mosaic(layers / "chemistry", meta["tiles"]["max_zoom"])
    overview.imshow(_masked(colours), extent=c_extent)
    places = _drill_places(inside)
    _drill_labels(overview, places)
    overview.plot(*habitat, "*", c="cyan", ms=16, mec="black")
    overview.set_xlim(whole[0], whole[2])
    overview.set_ylim(whole[1], whole[3])
    overview.legend(handles=_legend(meta), loc="lower left", fontsize=8)
    overview.set_title(
        f"Whole chemistry layer, 1 m tiles: APXS points by SO3; {len(inside)} APXS records on"
        f" drill tailings at {len(places)} places"
    )

    if inside:
        _drill_close_up(zoom, photo, layers / "chemistry", meta, inside, places)
    else:
        zoom.set_axis_off()
        zoom.set_title("No drill-tailings records in the walk area: no close-up")
    out = folder / "science.png"
    _save(fig, out)
    return out


def _drill_close_up(ax, photo, layer, meta, inside, places) -> None:
    """The chemistry tiles at full detail, 600 m round the drill records' centre."""
    cx = sum(d["x"] for d in inside) / len(inside)
    cy = sum(d["y"] for d in inside) / len(inside)
    box = (cx - 300, cy - 300, cx + 300, cy + 300)
    detail, p_extent = read_window(photo, box)
    _show_gray(ax, detail[::2, ::2], p_extent)
    colours, c_extent = _mosaic(layer, meta["tiles"]["max_zoom"], box)
    ax.imshow(_masked(colours), extent=c_extent)
    _drill_labels(
        ax, [p for p in places if box[0] <= p["x"] <= box[2] and box[1] <= p["y"] <= box[3]]
    )
    ax.set_xlim(box[0], box[2])
    ax.set_ylim(box[1], box[3])
    ax.set_title("Close-up, 600 m round the drill sites' centre, at full detail")


# Drill-tailings records this close share one label: the record does not say whether
# they are one hole (Nevado Sajama and Nevado Sajama2 sit 0.7 m apart).
DRILL_PLACE_M = 2.0


def _drill_places(drilled) -> list[dict]:
    """Drill-tailings records grouped by place, each {"x", "y", "label"}."""
    places: list[dict] = []
    for d in drilled:
        near = next(
            (p for p in places if math.dist((p["x"], p["y"]), (d["x"], d["y"])) <= DRILL_PLACE_M),
            None,
        )
        if near is None:
            near = {"x": d["x"], "y": d["y"], "records": []}
            places.append(near)
        near["records"].append(f"{d['name']} (sol {d['sol']})")
    return [{"x": p["x"], "y": p["y"], "label": ", ".join(p["records"])} for p in places]


def _drill_labels(ax, places) -> None:
    # Each label one line lower than the last, so places metres apart stay readable.
    for i, p in enumerate(places):
        ax.annotate(
            p["label"], (p["x"], p["y"]), color="cyan", fontsize=8,
            xytext=(8, -4 - 11 * i), textcoords="offset points",
            arrowprops={"arrowstyle": "-", "color": "cyan", "lw": 0.5},
        )  # fmt: skip


def _targets(ax, targets, ms) -> None:
    for t in targets:
        marker = "^" if t["kind"] == "ridge" else "v"
        ax.plot(t["x"], t["y"], marker, c="lime", ms=ms, mec="black")


def _target_handles() -> list:
    return [
        plt.Line2D([], [], ls="", marker="^", c="lime", mec="black", label="ridge target"),
        plt.Line2D([], [], ls="", marker="v", c="lime", mec="black", label="hollow target"),
    ]


def _legend(meta: dict) -> list:
    return [Patch(color=e["color"], label=e["label"]) for e in meta["legend"]]


def _masked(rgba: np.ndarray) -> np.ndarray:
    """An RGBA tile mosaic as floats, so matplotlib keeps its transparency."""
    return rgba.astype(np.float32) / 255.0


def _track(ax, track) -> None:
    ax.plot([p[0] for p in track], [p[1] for p in track], "-", c="red", lw=1, label="Curiosity")
