from __future__ import annotations

import csv
import io
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
import yaml
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from PIL import Image
from scipy.ndimage import map_coordinates

from contracts.models.common import Provenance, TerrainType
from contracts.models.site import SiteConfig
from contracts.paths import REPO_ROOT
from locate.drone.ground import straighten
from locate.drone.label import read_drone_frame
from prep.common import sha256, written_atomically
from prep.jezero.site_frame import SITE_PROJ
from route.tie_points import TiePointFit, fit_tie_points


@dataclass(frozen=True)
class KeyFrame:
    photo_id: str
    flight: int
    projection: str
    image: np.ndarray
    valid: np.ndarray
    reference_px: tuple[float, float]
    heading_deg: float
    crop: Path
    inputs: tuple[Path, ...]


@dataclass(frozen=True)
class PackFrame:
    photo_id: str
    flight: int
    hard_mode: bool
    projection: str
    photo: Path
    label: Path
    crop: Path
    inputs: tuple[Path, ...]


def read_pack(root: Path, site_path: Path = REPO_ROOT / "sites" / "jezero.yaml") -> list[PackFrame]:
    root, site_path = root.resolve(), site_path.resolve()
    site = SiteConfig.model_validate(yaml.safe_load(site_path.read_text()))
    if site.site != "jezero" or rasterio.CRS.from_string(
        site.projection
    ) != rasterio.CRS.from_string(SITE_PROJ):
        raise ValueError("use the reprojected Jezero pack, whose map metres are ground metres")
    index = _data_path(root, site.files["frame_list"])
    with index.open(newline="") as source:
        rows = list(csv.DictReader(source))
    frames = []
    for row in rows:
        flight, sol = int(row["flight"]), int(row["sol"])
        name, product = row["frame_png"], row["product"]
        if any(Path(n).name != n for n in (name, product, row["crop"])):
            raise ValueError("frame and crop names in frames.csv must not contain directories")
        if row["hard_mode"].lower() not in {"true", "false"}:
            raise ValueError("frames.csv hard_mode must be True or False")
        photo_id = Path(name).stem
        if Path(product).stem != photo_id:
            raise ValueError("the photo and its PDS product must have the same id")
        photo = _data_path(root, f"jezero/pack/frames/{name}")
        label = _data_path(root, f"jezero/source/helicam/sol-{sol:05d}/{photo_id}.xml")
        crop = _data_path(root, site.files[f"crop_flight_{flight:02d}"])
        if crop.name != row["crop"]:
            raise ValueError("frames.csv and the site config disagree about the flight's crop")
        frames.append(
            PackFrame(
                photo_id=photo_id,
                flight=flight,
                hard_mode=row["hard_mode"].lower() == "true",
                projection=site.projection,
                photo=photo,
                label=label,
                crop=crop,
                inputs=(photo, label, index, site_path),
            )
        )
    if len({f.photo_id for f in frames}) != len(frames):
        raise ValueError("frames.csv contains duplicate photo ids")
    return frames


def load_key_frame(frame: PackFrame) -> KeyFrame:
    camera = read_drone_frame(frame.label.read_text())
    if camera.file_stem != frame.photo_id or camera.flight != frame.flight:
        raise ValueError("the PDS label does not belong to this photo and flight")
    with Image.open(frame.photo) as photo:
        image = np.asarray(photo.convert("L"))
    ground = straighten(image, camera, resolution=0.25)
    result = KeyFrame(
        photo_id=frame.photo_id,
        flight=frame.flight,
        projection=frame.projection,
        image=ground.image,
        valid=ground.valid,
        reference_px=tuple(float(v) for v in ground.nadir_px),
        heading_deg=ground.heading_deg,
        crop=frame.crop,
        inputs=frame.inputs,
    )
    read_crop(result)
    return result


def _data_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError("pack inputs must stay inside REDMARK_DATA")
    return path


def save_answer(
    root: Path,
    frame: KeyFrame,
    photo_px: np.ndarray,
    map_xy: np.ndarray,
    *,
    terrain_type: str,
    hard_mode: bool,
    reviewed: bool,
    simulated: bool,
) -> Path:
    if not reviewed:
        raise ValueError("preview and check the overlay before saving an answer key")
    terrain = TerrainType(terrain_type)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", frame.photo_id) or frame.flight < 1:
        raise ValueError("a safe photo id and a positive flight number are required")
    root = root.resolve()
    photo, positions = np.asarray(photo_px, dtype=float), np.asarray(map_xy, dtype=float)
    fit = fit_tie_points(photo, positions, frame.reference_px, frame.heading_deg)
    height, width = frame.image.shape
    if np.any(photo < 0) or np.any(photo > [width - 1, height - 1]):
        raise ValueError("tie points must be on the visible photo")
    cols, rows = np.rint(photo).astype(int).T
    if not frame.valid[rows, cols].all():
        raise ValueError("tie points must be on the visible photo")
    with rasterio.open(frame.crop) as crop:
        for position, value in zip(positions, crop.sample(positions, masked=True), strict=True):
            row, col = crop.index(*position)
            if (
                not (0 <= row < crop.height and 0 <= col < crop.width)
                or np.ma.getmaskarray(value).any()
                or not np.isfinite(value.filled(0)).all()
            ):
                raise ValueError("tie points must be on the visible map, not outside or on no data")
    folder = root / "jezero" / "answer-key"
    path = folder / "keys" / f"{frame.photo_id}.json"
    overlay = folder / "overlays" / f"{frame.photo_id}.png"
    if path.exists() or overlay.exists():
        raise FileExistsError(
            f"{frame.photo_id} already has a key or overlay; nothing was replaced"
        )
    inputs = sorted({p.resolve() for p in (*frame.inputs, frame.crop)})
    provenance = Provenance(
        script="route/key_frames.py",
        commit=subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip(),
        inputs=[
            {
                "path": (
                    p.relative_to(root) if p.is_relative_to(root) else p.relative_to(REPO_ROOT)
                ).as_posix(),
                "sha256": sha256(p),
            }
            for p in inputs
        ],
    )
    canvas = Figure(figsize=(15, 5), layout="constrained")
    FigureCanvasAgg(canvas)
    draw_overlay(canvas, frame, photo, positions, fit, simulated=simulated)
    image = io.BytesIO()
    canvas.savefig(image, format="png", dpi=110)
    record = {
        "photo_id": frame.photo_id,
        "site": "jezero",
        "flight": frame.flight,
        "projection": frame.projection,
        "true_position": {"x": fit.position[0], "y": fit.position[1]},
        "true_heading_deg": fit.heading_deg,
        "terrain_type": terrain.value,
        "hard_mode": hard_mode,
        "simulated": simulated,
        "checked_by_eye": reviewed,
        "pixel_frame": "rectified north-up; pixel centres at integer (sample, line)",
        "reference_px": list(frame.reference_px),
        "rectified_heading_deg": frame.heading_deg,
        "tie_points": [
            {"photo_px": p.tolist(), "map_xy": xy.tolist()}
            for p, xy in zip(photo, positions, strict=True)
        ],
        "homography": fit.transform.tolist(),
        "fit_residual_m": fit.residual_m,
        "overlay": overlay.relative_to(root).as_posix(),
        "provenance": provenance.model_dump(mode="json"),
    }
    payloads = (
        (overlay, image.getvalue()),
        (path, (json.dumps(record, indent=2, allow_nan=False) + "\n").encode("utf-8")),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    overlay.parent.mkdir(parents=True, exist_ok=True)
    flights_path = folder / "flights.json"
    flights = json.loads(flights_path.read_text()) if flights_path.exists() else {}
    exclusions = {
        "site": "jezero",
        "excluded_flights": sorted(set(flights.get("excluded_flights", [])) | {frame.flight}),
        "photo_ids": sorted(set(flights.get("photo_ids", [])) | {frame.photo_id}),
        "rule": "No frame from these flights may be used for tuning.",
    }
    with written_atomically(flights_path) as partial:
        partial.write_text(json.dumps(exclusions, indent=2) + "\n", encoding="utf-8")
    created = []
    try:
        for destination, contents in payloads:
            with destination.open("xb") as output:
                created.append(destination)
                output.write(contents)
    except OSError:
        for destination in reversed(created):
            destination.unlink(missing_ok=True)
        raise
    return path


def draw_overlay(
    figure: Figure,
    frame: KeyFrame,
    photo_px: np.ndarray,
    map_xy: np.ndarray,
    fit: TiePointFit,
    *,
    simulated: bool,
) -> None:
    figure.clear()
    photo_ax, map_ax, aligned_ax = figure.subplots(1, 3)
    base, extent = read_crop(frame)
    photo_ax.imshow(np.ma.masked_where(~frame.valid, frame.image), cmap="gray")
    photo_ax.plot(*frame.reference_px, "c+", ms=12)
    for index, (pixel, position) in enumerate(zip(photo_px, map_xy, strict=True), 1):
        for ax, point in ((photo_ax, pixel), (map_ax, position), (aligned_ax, position)):
            ax.plot(*point, "o", mfc="none", mec="lime", ms=9)
            ax.annotate(str(index), point, xytext=(5, 5), textcoords="offset points", color="lime")
    height, width = frame.image.shape
    outline = fit.to_map(
        np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]])
    )
    closed = np.vstack([outline, outline[0]])
    for ax in (map_ax, aligned_ax):
        ax.imshow(base, cmap="gray", extent=extent)
        ax.plot(closed[:, 0], closed[:, 1], color="yellow", lw=1)
        ax.plot(*fit.position, "c+", ms=12)
        ax.ticklabel_format(useOffset=False, style="plain")
        ax.tick_params(labelsize=7)
        ax.set_xlabel("easting, ground metres")
        ax.set_ylabel("northing, ground metres")
    west, south = outline.min(axis=0)
    east, north = outline.max(axis=0)
    dx, dy = (east - west) / 500, (north - south) / 500
    xs, ys = np.meshgrid(west + (np.arange(500) + 0.5) * dx, north - (np.arange(500) + 0.5) * dy)
    target = np.column_stack([xs.ravel(), ys.ravel(), np.ones(xs.size)])
    source = target @ np.linalg.inv(fit.transform).T
    source = source[:, :2] / source[:, 2, None]
    sample = [source[:, 1], source[:, 0]]
    grey = map_coordinates(frame.image.astype(float), sample, order=1, mode="constant") / 255
    alpha = map_coordinates(frame.valid.astype(float), sample, order=0, mode="constant") * 0.55
    rgba = np.column_stack([grey, grey, grey, alpha]).reshape(500, 500, 4)
    aligned_ax.imshow(rgba, extent=(west, east, south, north))
    margin = max(east - west, north - south) * 0.1
    aligned_ax.set_xlim(west - margin, east + margin)
    aligned_ax.set_ylim(south - margin, north + margin)
    heading = np.radians(fit.heading_deg)
    aligned_ax.annotate(
        "",
        xy=np.asarray(fit.position) + margin * np.array([np.sin(heading), np.cos(heading)]),
        xytext=fit.position,
        arrowprops={"color": "cyan", "width": 2},
    )
    photo_ax.set_title("Rectified photo: numbered tie points")
    map_ax.set_title("Footprint on the Jezero photo map")
    aligned_ax.set_title("Photo at 55% opacity over the map")
    label = "SIMULATED fixture" if simulated else "Human tie-point answer key"
    figure.suptitle(
        f"{label}: {frame.photo_id}, flight {frame.flight}\n"
        f"({fit.position[0]:.3f}, {fit.position[1]:.3f}) m; heading {fit.heading_deg:.2f} degrees; "
        f"fit residual {fit.residual_m:.3f} m (not measured position error)"
    )


def read_crop(frame: KeyFrame) -> tuple[np.ma.MaskedArray, tuple[float, float, float, float]]:
    with rasterio.open(frame.crop) as src:
        if src.crs != rasterio.CRS.from_string(frame.projection):
            raise ValueError("the crop must use the Jezero site's ground-metre projection")
        if src.transform.b or src.transform.d or src.transform.a <= 0 or src.transform.e >= 0:
            raise ValueError("the map crop must be north-up")
        scale = max(src.height, src.width) / 1200
        shape = (
            max(1, round(src.height / max(scale, 1))),
            max(1, round(src.width / max(scale, 1))),
        )
        image = src.read(1, out_shape=shape, masked=True)
        b = src.bounds
        return image, (b.left, b.right, b.bottom, b.top)
