"""Build layer 5, location quality, for Gale (P3-05 landmark visibility, P3-06 final).

For every 1 m cell of the walk area in sites/gale.yaml: which of the four
landmarks in landmarks.yaml an eye OBSERVER_HEIGHT_M above the ground can see,
over the same terrain as the horizon grid (the 1 m Gale terrain, its 10 m copy,
and the HRSC and MOLA blend for the far rim and Mount Sharp, with curvature);
the error map, the median horizon fix error the horizon test measured for the
cell's class (error_map.py, from results/horizon/horizon-gale.json); and the
location-quality score, the share of landmarks in view scaled by that error.
Then checkpoint candidates (checkpoints.py) and lost-mode landmark directions
for each leg of the demo route in the demo cache (directions.py).

Writes, under REDMARK_DATA:
- gale/layers/landmark_<id>/ for each landmark, gale/layers/error_map/ and
  gale/layers/location_quality/ for the score: layer.json and tiles, in the
  layer contract, for the app;
- gale/rasters/location_quality.tif and gale/rasters/error_map.tif: the score
  and the error map as GeoTIFFs, for the route.

And in the repo:
- layers/location_quality/layer5-gale.json: the landmark points found, how much
  of the walk area sees each, the error map's medians and class shares, the
  spot checks (ridge tops against hollows), checkpoint candidates with their
  landmark view, landmark directions per leg, computing time, and the script,
  commit and input checksums;
- layers/location_quality/overlays/p3-05-layer5.png and p3-06-layer5-final.png:
  the overlays to check by eye.

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
from contracts.models.route_response import RouteResponse  # noqa: E402
from contracts.paths import REPO_ROOT, data_root  # noqa: E402
from layers.location_quality.checkpoints import checkpoint_candidates  # noqa: E402
from layers.location_quality.directions import landmark_view, leg_directions  # noqa: E402
from layers.location_quality.error_map import (  # noqa: E402
    CellTerrain,
    classify_cells,
    error_map,
    location_quality_score,
    read_medians,
)
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
FINAL_OVERLAY = HERE / "overlays" / "p3-06-layer5-final.png"
SCORE_LAYER = "location_quality"
SCORE_RASTER = "gale/rasters/location_quality.tif"
ERROR_LAYER = "error_map"
ERROR_RASTER = "gale/rasters/error_map.tif"
HORIZON_TEST = REPO_ROOT / "results" / "horizon" / "horizon-gale.json"
"""The horizon test summary the error map takes its medians from (P3-03)."""
DEMO_ROUTE = REPO_ROOT / "cache" / "demo" / "route" / "planning-route-fastest.json"
"""The demo route the landmark directions follow: its saved POST /route response."""
CHECKPOINT_SQUARE_M = 500.0
"""Each square of the walk area this size gives one checkpoint candidate."""
CHECKPOINT_NEIGHBOURHOOD_M = 10.0
"""A tie between candidates goes to the better mean score within this distance."""
DIRECTION_STEP_M = 10.0
OVERLAY_CANDIDATES = 12
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
# Viridis, dark (no landmark seen) to bright (all four from the best-measured ground).
SCORE_LEGEND = [
    LegendClass("Score 0: no landmark in view", "#440154", 0.0),
    LegendClass("Score 0.25", "#3b528b", 0.25),
    LegendClass("Score 0.5", "#21918c", 0.5),
    LegendClass("Score 0.75", "#5ec962", 0.75),
    LegendClass("Score 1: all 4 landmarks, best-measured ground", "#fde725", 1.0),
]
LANDMARK_SHARE_LABELS = [
    ("No landmark in view", 0.0),
    ("1 of 4 landmarks", 0.25),
    ("2 of 4 landmarks", 0.5),
    ("3 of 4 landmarks", 0.75),
    ("All 4 landmarks", 1.0),
]
MASK_LEGEND = [LegendClass("In view", "#fde725", 1.0), LegendClass("Hidden", "#440154", 0.0)]


def main() -> None:
    site = read_site_config()
    root = data_root()
    missing = [name for name in (GALE_DEM, FAR_DEM, PLACES) if not (root / name).exists()]
    if missing:
        sys.exit(f"{', '.join(missing)} not in {root}: set REDMARK_DATA to the data folder")
    # Before anything is written: layer 5 code, the horizon terrain code it uses, the
    # landmarks and the site config must be committed, or the recorded commit can't
    # reproduce the layers.
    commit = git_commit(
        "layers/location_quality/*.py",
        "locate/horizon/*.py",
        LANDMARKS_FILE,
        SITE_CONFIG,
        HORIZON_TEST,
        DEMO_ROUTE,
    )
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
    share = location_quality(masks)
    terrain_cells = _classify(gale.terrain, cells)
    medians = read_medians(HORIZON_TEST)
    errors = error_map(terrain_cells, medians)
    score = location_quality_score(share, errors, lowest_m=medians.lowest_m)
    candidates = checkpoint_candidates(
        score,
        terrain_cells.hollow,
        cells,
        square_m=CHECKPOINT_SQUARE_M,
        neighbourhood_m=CHECKPOINT_NEIGHBOURHOOD_M,
    )
    route = RouteResponse.model_validate(json.loads(DEMO_ROUTE.read_text())["response"])
    directions = leg_directions(
        [p.model_dump() for p in route.path],
        [leg.model_dump() for leg in route.legs],
        landmarks,
        masks,
        cells,
        step_m=DIRECTION_STEP_M,
    )
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
    error_legend = [
        LegendClass(f"Textured ground: {medians.textured_m:.0f} m", "#fde725", medians.textured_m),
        LegendClass(f"Plain ground: {medians.plain_m:.0f} m", "#21918c", medians.plain_m),
        LegendClass(f"Hollow: {medians.hollow_m:.0f} m", "#440154", medians.hollow_m),
    ]
    write_tile_layer(
        layers_dir / ERROR_LAYER,
        errors,
        cells,
        title="Error map: median horizon fix error measured on the hidden pile",
        units="ground metres",
        legend=error_legend,
        sources=[(name, url) for name, url in SOURCES],
    )
    write_geotiff(root / ERROR_RASTER, errors, cells, site.projection)
    write_tile_layer(
        layers_dir / SCORE_LAYER,
        score,
        cells,
        title="Location quality: landmarks in view and measured error",
        units="score, 0 to 1",
        legend=SCORE_LEGEND,
        sources=[(name, url) for name, url in SOURCES],
    )
    write_geotiff(root / SCORE_RASTER, score, cells, site.projection)

    ground = _ground(gale.terrain, cells)
    relief = _relief(ground, cells.res)
    base_map = read_layer_image(root / site.files["base_map"], pixels_across=1000)
    spot = spot_check(share, relief)
    known = terrain_cells.known
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
        "landmark_shares": {
            label: round(float(np.isclose(share, value).mean()), 4)
            for label, value in LANDMARK_SHARE_LABELS
        },
        "spot_check": spot,
        "error_map": {
            "test_summary": HORIZON_TEST.relative_to(REPO_ROOT).as_posix(),
            "median_error_m": {
                "textured": medians.textured_m,
                "plain": medians.plain_m,
                "hollow": medians.hollow_m,
            },
            "share_of_walk_area": {
                "textured": round(
                    float((terrain_cells.textured & ~terrain_cells.hollow).mean()), 4
                ),
                "plain": round(
                    float((known & ~terrain_cells.textured & ~terrain_cells.hollow).mean()), 4
                ),
                "hollow": round(float(terrain_cells.hollow.mean()), 4),
                "unknown": round(float((~known).mean()), 4),
            },
        },
        "score": (
            "share of the landmarks in view x the lowest class median error"
            " / the cell's median error"
        ),
        "spot_check_score": spot_check(score, relief),
        "checkpoint_candidates": [
            _candidate(i, at, landmarks, masks, cells, score, errors, terrain_cells)
            for i, at in enumerate(candidates)
        ],
        "checkpoint_square_m": CHECKPOINT_SQUARE_M,
        "landmark_directions": {
            "route": DEMO_ROUTE.relative_to(REPO_ROOT).as_posix(),
            "mode": route.mode.value,
            "step_m": DIRECTION_STEP_M,
            "legs": directions,
        },
        "layers": [f"landmark_{lm.id}" for lm in landmarks] + [ERROR_LAYER, SCORE_LAYER],
        "score_raster": SCORE_RASTER,
        "error_raster": ERROR_RASTER,
        "terrain_load_s": round(loaded - started, 1),
        "compute_s": round(computed - loaded, 1),
        "provenance": _provenance(root, base_map, commit).model_dump(mode="json"),
    }
    SUMMARY.write_text(json.dumps(summary, indent=2) + "\n")
    draw_overlay(OVERLAY, gale.terrain, landmarks, masks, share, relief, cells, base_map, spot)
    draw_final_overlay(FINAL_OVERLAY, errors, score, cells, base_map, summary, route, error_legend)
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
            "mean_score": round(float(np.nanmean(score[mask])), 4) if mask.any() else None,
        }
        for name, mask in classes.items()
    }


def _classify(terrain: Terrain, cells: Cells) -> CellTerrain:
    """Each cell's terrain type and hollow flag, from ground reaching HOLLOW_RADIUS_M past the
    walk area's edge, so cells at the edge are judged on a full circle like the tested stops."""
    pad = int(np.ceil(HOLLOW_RADIUS_M / cells.res)) + 1
    padded = Cells(
        left=cells.left - pad * cells.res,
        top=cells.top + pad * cells.res,
        res=cells.res,
        shape=(cells.shape[0] + 2 * pad, cells.shape[1] + 2 * pad),
    )
    full = classify_cells(_ground(terrain, padded), cells.res)
    inner = (slice(pad, -pad), slice(pad, -pad))
    return CellTerrain(full.textured[inner], full.hollow[inner], full.known[inner])


def _candidate(
    number: int,
    at: tuple[float, float],
    landmarks: list[Landmark],
    masks: dict[str, np.ndarray],
    cells: Cells,
    score: np.ndarray,
    errors: np.ndarray,
    terrain_cells: CellTerrain,
) -> dict:
    row = int((cells.top - at[1]) // cells.res)
    col = int((at[0] - cells.left) // cells.res)
    return {
        "id": f"candidate-{number + 1}",
        "position": {"x": at[0], "y": at[1]},
        "score": round(float(score[row, col]), 4),
        "expected_error_m": float(errors[row, col]),
        "terrain_type": "textured" if terrain_cells.textured[row, col] else "plain",
        "landmarks_in_view": landmark_view(landmarks, masks, cells, at),
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


def _provenance(root: Path, base_map: LayerImage, commit: str) -> Provenance:
    data = [root / GALE_DEM, root / FAR_DEM, root / PLACES, *base_map.files]
    repo = [SITE_CONFIG, LANDMARKS_FILE, HORIZON_TEST, DEMO_ROUTE]
    inputs = [
        {"path": p.resolve().relative_to(root.resolve()).as_posix(), "sha256": sha256_file(p)}
        for p in data
    ] + [{"path": p.relative_to(REPO_ROOT).as_posix(), "sha256": sha256_file(p)} for p in repo]
    return Provenance(script="layers/location_quality/build.py", commit=commit, inputs=inputs)


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
    ax.set_title(f"Landmarks in view (on {base_map.title})")

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


def draw_final_overlay(
    path: Path,
    errors: np.ndarray,
    score: np.ndarray,
    cells: Cells,
    base_map: LayerImage,
    summary: dict,
    route: RouteResponse,
    error_legend: list[LegendClass],
) -> None:
    """The error map, and the score with the checkpoint candidates and the demo route,
    on the base map; then the directions each leg of the route gets."""
    step = max(1, round(score.shape[1] / 1000))
    extent = (cells.left, cells.right, cells.bottom, cells.top)
    fig, axes = plt.subplots(1, 3, figsize=(32, 11), width_ratios=[1, 1.15, 0.9])

    ax = axes[0]
    ax.imshow(base_map.image, extent=base_map.extent)
    rgba = np.zeros((*errors[::step, ::step].shape, 4))
    for c in error_legend:
        hit = np.isclose(errors[::step, ::step], c.value)
        rgba[hit] = [int(c.color[i : i + 2], 16) / 255 for i in (1, 3, 5)] + [0.7]
    ax.imshow(rgba, extent=extent)
    for c in error_legend:
        ax.plot([], [], "s", color=c.color, ms=10, label=c.label)
    ax.legend(loc="lower left", title="median horizon fix error")
    ax.set_xlim(extent[:2])
    ax.set_ylim(extent[2:])
    ax.set_title(f"Error map, from {summary['error_map']['test_summary']}")

    ax = axes[1]
    ax.imshow(base_map.image, extent=base_map.extent)
    image = ax.imshow(
        score[::step, ::step], extent=extent, cmap="viridis", vmin=0, vmax=1, alpha=0.75
    )
    fig.colorbar(image, ax=ax, shrink=0.8, label="location-quality score")
    xs = [p.x for p in route.path]
    ys = [p.y for p in route.path]
    ax.plot(xs, ys, "-", color="white", lw=2.5)
    ax.plot(xs, ys, "-", color="#d62728", lw=1.2, label=f"demo route ({route.mode.value})")
    for leg in summary["landmark_directions"]["legs"]:
        a, b = route.path[leg["start_index"]], route.path[leg["end_index"]]
        ax.annotate(
            f"leg {leg['leg'] + 1}",
            ((a.x + b.x) / 2, (a.y + b.y) / 2),
            color="white",
            fontsize=10,
            weight="bold",
        )
    for c in summary["checkpoint_candidates"]:
        x, y = c["position"]["x"], c["position"]["y"]
        ax.plot(x, y, "*", color="#ff7f0e", mec="black", ms=16)
        ax.annotate(c["id"].split("-")[-1], (x, y), xytext=(6, 6), textcoords="offset points")
    ax.plot([], [], "*", color="#ff7f0e", mec="black", ms=12, label="checkpoint candidate")
    ax.legend(loc="lower left")
    ax.set_xlim(extent[:2])
    ax.set_ylim(extent[2:])
    ax.set_title("Location quality: landmarks in view x measured error")

    ax = axes[2]
    ax.axis("off")
    lines = [f"Demo route ({summary['landmark_directions']['route']}):"]
    for leg in summary["landmark_directions"]["legs"]:
        seen = ", ".join(
            f"{v['id']} {v['side']} {v['share_of_leg_in_view']:.0%}"
            for v in leg["landmarks"]
            if v["side"]
        )
        lines.append(f"  leg {leg['leg'] + 1}, heading {leg['heading_deg']:.0f}°:")
        lines.append(f'    "{leg["text"]}"')
        lines.append(f"    in view: {seen or 'none'}")
    lines.append("")
    shown = summary["checkpoint_candidates"][:OVERLAY_CANDIDATES]
    lines.append(
        f"Best {len(shown)} of {len(summary['checkpoint_candidates'])} checkpoint candidates"
        " (score, expected error, landmarks in view);"
    )
    lines.append("the rest are in layer5-gale.json:")
    for c in shown:
        view = ", ".join(f"{v['id']} {v['heading_deg']:.0f}°" for v in c["landmarks_in_view"])
        lines.append(
            f"  {c['id'].split('-')[-1]}: {c['score']:.2f}, {c['expected_error_m']:.0f} m,"
            f" {c['terrain_type']}; {view}"
        )
    ax.text(0, 1, "\n".join(lines), va="top", family="monospace", fontsize=10)
    fig.suptitle(
        "P3-06 layer 5 final at Gale: error map, score, checkpoints, directions", fontsize=16
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=70)
    plt.close(fig)


if __name__ == "__main__":
    main()
