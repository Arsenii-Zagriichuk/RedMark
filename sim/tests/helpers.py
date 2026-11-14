import json
from pathlib import Path

import numpy as np
import rasterio
import yaml
from rasterio.transform import from_origin

from contracts.paths import REPO_ROOT


def walk(path, fixes=(), seed=1, **break_it) -> dict:
    return {
        "site": "gale",
        "path": [{"x": x, "y": y} for x, y in path],
        "fix_schedule": [{"time_s": t, "method": m} for t, m in fixes],
        "break_it": {"camera_off": False, "radio_off": False, "drone_grounded": False} | break_it,
        "seed": seed,
    }


def write_summary(
    results_root: Path,
    median_error_m: float,
    relative_path: str = "horizon/horizon-gale.json",
) -> None:
    summary = json.loads((REPO_ROOT / "results" / relative_path).read_text())
    summary["overall"]["median_error_m"] = median_error_m
    target = results_root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(summary))


def write_terrain(
    tmp_path, monkeypatch, *, raster_projection=None, raster_transform=None, **layers
):
    sites = tmp_path / "sites"
    sites.mkdir()
    data = tmp_path / "data"
    data.mkdir()
    site = yaml.safe_load((REPO_ROOT / "sites" / "gale.yaml").read_text())
    site["files"] = {name: f"{name}.tif" for name in layers}
    for name, values in layers.items():
        band = np.asarray(values, dtype="float32")
        site["bounds"] = {
            "min_x": -100,
            "min_y": 100 - 100 * band.shape[0],
            "max_x": -100 + 100 * band.shape[1],
            "max_y": 100,
        }
        with rasterio.open(
            data / f"{name}.tif",
            "w",
            driver="GTiff",
            width=band.shape[1],
            height=band.shape[0],
            count=1,
            dtype=band.dtype,
            crs=raster_projection or site["projection"],
            transform=raster_transform or from_origin(-100, 100, 100, 100),
            nodata=-9999,
        ) as raster:
            raster.write(band, 1)
    (sites / "gale.yaml").write_text(yaml.safe_dump(site))
    monkeypatch.setenv("REDMARK_DATA", str(data))
    return sites
