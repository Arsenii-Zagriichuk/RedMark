"""Ingenuity flight paths from NASA's flight-path GeoJSON, in the site frame."""

import json
from pathlib import Path

from prep.jezero.crop import Bounds
from prep.jezero.frame import to_site_frame

Path2D = list[tuple[float, float]]


def load_flight_paths(geojson: Path) -> dict[int, Path2D]:
    """Flight number to its ground track in site-frame metres, in flight order."""
    features = json.loads(geojson.read_text())["features"]
    return {
        int(f["properties"]["Flight"]): [to_site_frame(lon, lat) for lon, lat, *_ in coords]
        for f in features
        for coords in [f["geometry"]["coordinates"]]
    }


def flight_bounds(path: Path2D, margin: float) -> Bounds:
    """The track's bounding box grown by `margin` metres on every side."""
    xs = [x for x, _ in path]
    ys = [y for _, y in path]
    return (min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin)
