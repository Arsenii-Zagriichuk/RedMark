"""Ingenuity flights from NASA's flight-path GeoJSON, in the site frame."""

import json
from dataclasses import dataclass
from pathlib import Path

from prep.jezero.crop import Bounds
from prep.jezero.site_frame import to_site_frame

Path2D = list[tuple[float, float]]


@dataclass(frozen=True)
class Flight:
    sol: int
    path: Path2D  # ground track in site-frame metres, in flight order


def load_flights(geojson: Path) -> dict[int, Flight]:
    """Flight number to its sol and ground track."""
    features = json.loads(geojson.read_text())["features"]
    return {
        int(f["properties"]["Flight"]): Flight(
            sol=int(f["properties"]["Sol"]),
            path=[to_site_frame(lon, lat) for lon, lat, *_ in f["geometry"]["coordinates"]],
        )
        for f in features
    }


def flight_bounds(path: Path2D, margin: float) -> Bounds:
    """The track's bounding box grown by `margin` metres on every side."""
    xs = [x for x, _ in path]
    ys = [y for _, y in path]
    return (min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin)
