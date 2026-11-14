"""Build layer 5, landmark visibility, for Gale (P3-05).

For every 1 m cell of the walk area in sites/gale.yaml: which of the four
landmarks in landmarks.yaml an eye OBSERVER_HEIGHT_M above the ground can see,
over the same terrain as the horizon grid (the 1 m Gale terrain, its 10 m copy,
and the HRSC and MOLA blend for the far rim and Mount Sharp, with curvature).
The combined score is the share of the four a cell sees.

Writes, under REDMARK_DATA:
- gale/layers/landmark_<id>/ for each landmark and gale/layers/location_quality/
  for the score: layer.json and tiles, in the layer contract, for the app;
- gale/rasters/location_quality.tif: the score as a GeoTIFF, for the route.

And in the repo:
- layers/location_quality/layer5-gale.json: the landmark points found, how much
  of the walk area sees each, the spot check (ridge tops against hollows),
  computing time, and the script, commit and input checksums;
- layers/location_quality/overlays/p3-05-layer5.png: the overlay to check by eye.

Run with `uv run python -m layers.location_quality.build`. A new walk area or a
moved landmark is a rerun, not a code change.
"""

import json
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from scipy.signal import fftconvolve  # noqa: E402

from contracts.models.common import Provenance  # noqa: E402
from contracts.paths import REPO_ROOT, data_root  # noqa: E402
from layers.location_quality.landmarks import LANDMARKS_FILE, load_landmarks  # noqa: E402
from layers.location_quality.layer_files import (  # noqa: E402
    LegendClass,
    write_geotiff,
    write_tile_layer,
)
from layers.location_quality.visibility import (  # noqa: E402
    Cells,
    Landmark,
    landmark_masks,
    location_quality,
)
from locate.horizon.base_map import LayerImage, read_layer_image  # noqa: E402
from locate.horizon.fix import PLACES, SITE_CONFIG, read_site_config  # noqa: E402
from locate.horizon.grid import OBSERVER_HEIGHT_M  # noqa: E402
from locate.horizon.render import Terrain  # noqa: E402
from locate.horizon.sources import (  # noqa: E402
    FAR_DEM,
    GALE_DEM,
    git_commit,
    load_gale_terrain,
    sha256_file,
)
from locate.horizon.stop_terrain import HOLLOW_DEPTH_M, HOLLOW_RADIUS_M  # noqa: E402

CELL_M = 1.0
HERE = Path(__file__).parent
SUMMARY = HERE / "layer5-gale.json"
OVERLAY = HERE / "overlays" / "p3-05-layer5.png"
SCORE_LAYER = "location_quality"
SCORE_RASTER = "gale/rasters/location_quality.tif"
SOURCES = [
    (
        "MSL Gale DEM mosaic, 1 m, v3 (USGS Astrogeology)",
        "https://planetarymaps.usgs.gov/mosaic/Mars/MSL/MSL_Gale_DEM_Mosaic_1m_v3.tif",
    ),
    (
        "Mars HRSC and MOLA blended DEM, 200 m v2 (USGS Astrogeology)",
        "https://planetarymaps.usgs.gov/mosaic/Mars/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif",
    ),
]
# Viridis, dark (no landmark seen) to bright (all four).
SCORE_LEGEND = [
    LegendClass("No landmark in view", "#440154", 0.0),
    LegendClass("1 of 4 landmarks", "#3b528b", 0.25),
    LegendClass("2 of 4 landmarks", "#21918c", 0.5),
    LegendClass("3 of 4 landmarks", "#5ec962", 0.75),
    LegendClass("All 4 landmarks", "#fde725", 1.0),
]
MASK_LEGEND = [LegendClass("In view", "#fde725", 1.0), LegendClass("Hidden", "#440154", 0.0)]


def main() -> None:
    site = read_site_config()
    root = data_root()
    missing = [name for name in (GALE_DEM, FAR_DEM, PLACES) if not (root / name).exists()]
    if missing:
        sys.exit(f"{', '.join(missing)} not in {root}: set REDMARK_DATA to the data folder")
    started = time.perf_counter()
    gale = load_gale_terrain(root, site.bounds, root / "gale" / "horizon" / "cache")
    landmarks = load_landmarks(gale.terrain, site.bounds, root / PLACES)
    b = site.bounds
    cells = Cells(
        left=b.min_x,
        top=b.max_y,
        res=CELL_M,
        shape=(round((b.max_y - b.min_y) / CELL_M), round((b.max_x - b.min_x) / CELL_M)),
    )
    loaded = time.perf_counter()
    masks = {}
    for landmark in landmarks:
        masks |= landmark_masks(
            gale.terrain, [landmark], cells, observer_height_m=OBSERVER_HEIGHT_M
        )
        print(f"{landmark.id}: {masks[landmark.id].mean():.0%} of the walk area sees it")
    score = location_quality(masks)
    computed = time.perf_counter()

    layers_dir = root / "gale" / "layers"
    for landmark in landmarks:
        write_tile_layer(
            layers_dir / f"landmark_{landmark.id}",
            masks[landmark.id].astype(np.float32),
            cells,
            title=f"{landmark.title} in view",
            units="in view or hidden",
            legend=MASK_LEGEND,
            sources=[(name, url) for name, url in SOURCES],
        )
    write_tile_layer(
        layers_dir / SCORE_LAYER,
        score,
        cells,
        title="Location quality: landmarks in view",
        units="share of the 4 landmarks in view",
        legend=SCORE_LEGEND,
        sources=[(name, url) for name, url in SOURCES],
    )
    write_geotiff(root / SCORE_RASTER, score, cells, site.projection)

    ground = _ground(gale.terrain, cells)
    relief = _relief(ground, cells.res)
    base_map = read_layer_image(root / site.files["base_map"], pixels_across=1000)
    spot = spot_check(score, relief)
    summary = {
        "site": site.site.value,
        "walk_area": b.model_dump(),
        "resolution_m": CELL_M,
        "observer_height_m": OBSERVER_HEIGHT_M,
        "landmarks": [
            {
                "id": landmark.id,
                "title": landmark.title,
                "points": [
                    {
                        "x": round(x, 1),
                        "y": round(y, 1),
                        "height_m": round(float(_height(gale.terrain, x, y)), 1),
                    }
                    for x, y in landmark.points
                ],
                "body_radius_m": landmark.body_radius_m,
                "share_in_view": round(float(masks[landmark.id].mean()), 4),
            }
            for landmark in landmarks
        ],
        "score_shares": {
            c.label: round(float(np.isclose(score, c.value).mean()), 4) for c in SCORE_LEGEND
        },
        "spot_check": spot,
        "layers": [f"landmark_{lm.id}" for lm in landmarks] + [SCORE_LAYER],
        "score_raster": SCORE_RASTER,
        "terrain_load_s": round(loaded - started, 1),
        "compute_s": round(computed - loaded, 1),
        "provenance": _provenance(root, base_map).model_dump(mode="json"),
    }
    SUMMARY.write_text(json.dumps(summary, indent=2) + "\n")
    draw_overlay(OVERLAY, gale.terrain, landmarks, masks, score, relief, cells, base_map, spot)
    print(json.dumps({k: v for k, v in summary.items() if k != "provenance"}, indent=2))


def spot_check(score: np.ndarray, relief: np.ndarray) -> dict:
    """Mean score on ridge tops, open ground and in hollows. A hollow sits more
    than HOLLOW_DEPTH_M below the mean ground within HOLLOW_RADIUS_M (the horizon
    test's rule, locate/horizon/stop_terrain.py); a ridge top as far above it."""
    classes = {
        "ridge_top": relief > HOLLOW_DEPTH_M,
        "open_ground": np.abs(relief) <= HOLLOW_DEPTH_M,
        "hollow": relief < -HOLLOW_DEPTH_M,
    }
    return {
        name: {
            "share_of_walk_area": round(float(mask.mean()), 4),
            "mean_score": round(float(score[mask].mean()), 4) if mask.any() else None,
        }
        for name, mask in classes.items()
    }


def _ground(terrain: Terrain, cells: Cells) -> np.ndarray:
    xs, ys = cells.centres()
    out = np.empty(cells.shape, np.float32)
    for row, y in enumerate(ys):
        out[row] = terrain.height(xs, np.full_like(xs, y), np.zeros_like(xs))
    return out


def _relief(ground: np.ndarray, res_m: float) -> np.ndarray:
    """Each cell's height above the mean ground within HOLLOW_RADIUS_M (negative in a hollow).
    Near the walk area's edge the mean covers only the part of the circle inside it."""
    r = int(HOLLOW_RADIUS_M / res_m)
    yy, xx = np.mgrid[-r : r + 1, -r : r + 1]
    disk = (np.hypot(yy, xx) <= r).astype(np.float32)
    known = np.isfinite(ground).astype(np.float32)
    total = fftconvolve(np.where(known > 0, ground, 0.0), disk, mode="same")
    count = fftconvolve(known, disk, mode="same")
    return ground - total / np.maximum(count, 1.0)


def _height(terrain: Terrain, x: float, y: float) -> float:
    return terrain.height(np.array([x]), np.array([y]), np.array([np.inf]))[0]


def _provenance(root: Path, base_map: LayerImage) -> Provenance:
    data = [root / GALE_DEM, root / FAR_DEM, root / PLACES, *base_map.files]
    repo = [SITE_CONFIG, LANDMARKS_FILE]
    inputs = [
        {"path": p.resolve().relative_to(root.resolve()).as_posix(), "sha256": sha256_file(p)}
        for p in data
    ] + [{"path": p.relative_to(REPO_ROOT).as_posix(), "sha256": sha256_file(p)} for p in repo]
    return Provenance(script="layers/location_quality/build.py", commit=git_commit(), inputs=inputs)


def draw_overlay(
    path: Path,
    terrain: Terrain,
    landmarks: list[Landmark],
    masks: dict[str, np.ndarray],
    score: np.ndarray,
    relief: np.ndarray,
    cells: Cells,
    base_map: LayerImage,
    spot: dict,
) -> None:
    """Where the landmarks are; the score and each landmark's mask on the base
    map; and the spot check, ridge tops against hollows."""
    step = max(1, round(score.shape[1] / 1000))
    extent = (cells.left, cells.right, cells.bottom, cells.top)
    fig = plt.figure(figsize=(26, 13))
    grid = fig.add_gridspec(2, 4)

    ax = fig.add_subplot(grid[0, 0])
    far = terrain.tiers[-1].raster
    far_extent = (
        far.left,
        far.left + far.heights.shape[1] * far.res,
        far.top - far.heights.shape[0] * far.res,
        far.top,
    )
    ax.imshow(far.heights, extent=far_extent, cmap="gist_earth")
    ax.add_patch(
        plt.Rectangle(
            (cells.left, cells.bottom),
            cells.right - cells.left,
            cells.top - cells.bottom,
            fill=False,
            ec="red",
            lw=1.5,
        )
    )
    centre = ((cells.left + cells.right) / 2, (cells.bottom + cells.top) / 2)
    colours = dict(
        zip([lm.id for lm in landmarks], ["#d62728", "#ff7f0e", "#9467bd", "#17becf"], strict=False)
    )
    for landmark in landmarks:
        xs, ys = zip(*landmark.points, strict=True)
        ax.plot(xs, ys, "o", ms=5, color=colours[landmark.id], label=landmark.title)
        for x, y in landmark.points:
            ax.plot([centre[0], x], [centre[1], y], "-", lw=0.4, color=colours[landmark.id])
    span = 75_000
    ax.set_xlim(centre[0] - span, centre[0] + span)
    ax.set_ylim(centre[1] - span, centre[1] + span)
    ax.legend(loc="lower left", fontsize=8)
    ax.set_title("Landmark points (HRSC and MOLA terrain); red box: walk area")

    ax = fig.add_subplot(grid[0, 1])
    ax.imshow(base_map.image, extent=base_map.extent)
    image = ax.imshow(
        score[::step, ::step], extent=extent, cmap="viridis", vmin=0, vmax=1, alpha=0.75
    )
    fig.colorbar(image, ax=ax, shrink=0.7, label="share of the 4 landmarks in view")
    for landmark in landmarks[:3]:
        x, y = landmark.points[0]
        if extent[0] <= x <= extent[1] and extent[2] <= y <= extent[3]:
            ax.plot(x, y, "*", color=colours[landmark.id], ms=12)
    ax.set_xlim(extent[:2])
    ax.set_ylim(extent[2:])
    ax.set_title(f"Location quality (on {base_map.title})")

    ax = fig.add_subplot(grid[0, 2])
    ax.imshow(relief[::step, ::step], extent=extent, cmap="RdBu_r", vmin=-5, vmax=5)
    ax.set_title(
        f"Height above the mean ground within {HOLLOW_RADIUS_M:.0f} m (m): "
        "red ridge top, blue hollow"
    )

    ax = fig.add_subplot(grid[0, 3])
    names = list(spot)
    values = [spot[n]["mean_score"] or 0.0 for n in names]
    ax.bar(names, values, color=["#d62728", "#7f7f7f", "#1f77b4"])
    for i, n in enumerate(names):
        ax.text(
            i,
            values[i] + 0.01,
            f"{values[i]:.2f}\n({spot[n]['share_of_walk_area']:.0%} of area)",
            ha="center",
        )
    ax.set_ylim(0, 1)
    ax.set_ylabel("mean location-quality score")
    ax.set_title(f"Spot check: ridge tops vs hollows (±{HOLLOW_DEPTH_M:.0f} m)")

    for i, landmark in enumerate(landmarks):
        ax = fig.add_subplot(grid[1, i])
        ax.imshow(base_map.image, extent=base_map.extent)
        ax.imshow(
            masks[landmark.id][::step, ::step],
            extent=extent,
            cmap="viridis",
            vmin=0,
            vmax=1,
            alpha=0.7,
        )
        ax.set_xlim(extent[:2])
        ax.set_ylim(extent[2:])
        ax.set_title(f"{landmark.title}: {masks[landmark.id].mean():.0%} in view (bright)")
    fig.suptitle(
        "P3-05 layer 5, landmark visibility at Gale: 1 m cells, eye 1.9 m above the ground"
    )
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=70)
    plt.close(fig)


if __name__ == "__main__":
    main()
