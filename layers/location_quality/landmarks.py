"""Find the landmarks' points in the terrain, as landmarks.yaml describes them."""

from pathlib import Path

import numpy as np
import yaml

from contracts.models.common import Bounds
from layers.location_quality.visibility import Landmark
from locate.horizon.fix import rover_position
from locate.horizon.grid import OBSERVER_HEIGHT_M, ray_distances
from locate.horizon.render import MARS_RADIUS_M, Terrain

LANDMARKS_FILE = Path(__file__).with_name("landmarks.yaml")
# A summit search looks at this many points across the search circle's diameter.
SUMMIT_SEARCH_POINTS = 600
# A summit found further out than this share of the search radius is a slope running off the
# circle, not a summit.
SUMMIT_EDGE = 0.95


def load_landmarks(terrain: Terrain, walk_area: Bounds, places: Path) -> list[Landmark]:
    entries = yaml.safe_load(LANDMARKS_FILE.read_text())["landmarks"]
    centre = ((walk_area.min_x + walk_area.max_x) / 2, (walk_area.min_y + walk_area.max_y) / 2)
    landmarks = []
    for entry in entries:
        if "summit_of" in entry:
            s = entry["summit_of"]
            points = (summit(terrain, (s["x"], s["y"]), s["radius_m"]),)
        elif "skyline_point" in entry:
            s = entry["skyline_point"]
            at = rover_position(places, s["site"], s["drive"])
            points = (skyline_point(terrain, at, s["heading_deg"]),)
        elif "rim" in entry:
            r = entry["rim"]
            headings = (
                np.arange(
                    r["from_deg"],
                    r["to_deg"] + 360 * (r["to_deg"] < r["from_deg"]) + 1e-9,
                    r["step_deg"],
                )
                % 360
            )
            points = tuple(
                skyline_point(
                    terrain, centre, h, nearest_m=r["nearest_m"], farthest_m=r["farthest_m"]
                )
                for h in headings
            )
        else:
            raise ValueError(f"landmark {entry['id']}: no summit_of, skyline_point or rim")
        landmarks.append(Landmark(entry["id"], entry["title"], points, entry["body_radius_m"]))
    return landmarks


def summit(terrain: Terrain, centre: tuple[float, float], radius_m: float) -> tuple[float, float]:
    """The highest terrain within radius_m of centre, from the finest terrain there."""
    offsets = np.linspace(-radius_m, radius_m, SUMMIT_SEARCH_POINTS)
    dx, dy = np.meshgrid(offsets, offsets)
    inside = np.hypot(dx, dy) <= radius_m
    x, y = centre[0] + dx[inside], centre[1] + dy[inside]
    heights = terrain.height(x, y, np.zeros_like(x))
    best = np.nanargmax(heights)
    if np.hypot(dx[inside][best], dy[inside][best]) > SUMMIT_EDGE * radius_m:
        raise ValueError(
            f"the highest terrain within {radius_m:.0f} m of {centre} is on the search circle's"
            " edge: that is a slope, not a summit"
        )
    return float(x[best]), float(y[best])


def skyline_point(
    terrain: Terrain,
    at: tuple[float, float],
    heading_deg: float,
    *,
    nearest_m: float = 5.0,
    farthest_m: float = 120_000.0,
) -> tuple[float, float]:
    """The terrain between nearest_m and farthest_m that forms the skyline at
    heading_deg, seen from an eye OBSERVER_HEIGHT_M above the ground at `at`
    (curvature as in the horizon renderer)."""
    distances = ray_distances(nearest_m, farthest_m, 1.0, 0.1)
    az = np.radians(heading_deg)
    x, y = at[0] + distances * np.sin(az), at[1] + distances * np.cos(az)
    ground = terrain.height(np.array([at[0]]), np.array([at[1]]), np.array([0.0]))[0]
    eye = MARS_RADIUS_M + ground + OBSERVER_HEIGHT_M
    radius = MARS_RADIUS_M + terrain.height(x, y, distances)
    angle = distances / MARS_RADIUS_M
    elevation = np.arctan2(radius * np.cos(angle) - eye, radius * np.sin(angle))
    best = np.nanargmax(elevation)
    return float(x[best]), float(y[best])
