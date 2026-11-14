"""Lost-mode landmark directions along a route, and a checkpoint's landmark view (P3-06).

For each leg of a route: which landmarks the crew can see along it, and where
each sits against the way they walk. The leg is sampled every step_m; at each
sample the landmark's bearing is compared with the heading of the path there,
so a leg that bends is judged where the crew actually faces. A landmark's side
comes from the mean of those angles over the samples that see it:

- within AHEAD_DEG of the heading: "Walk towards Texoli";
- beyond BEHIND_DEG: "Keep the Gale crater rim behind you";
- otherwise "Keep the upper Mount Sharp peak on your left" (or right).

A leg's direction uses the first landmark, in landmarks.yaml's order, in view
from at least MIN_SHARE_IN_VIEW of the leg; with none, the leg has no direction.
A landmark of several points (the crater rim) lies at the mean of their bearings.
Headings are degrees clockwise from map north.
"""

import math

import numpy as np

from layers.location_quality.visibility import Cells, Landmark

AHEAD_DEG = 30.0
BEHIND_DEG = 150.0
MIN_SHARE_IN_VIEW = 0.5


def bearing_deg(at: tuple[float, float], to: tuple[float, float]) -> float:
    """Heading from `at` to `to`, degrees clockwise from map north, in [0, 360)."""
    return math.degrees(math.atan2(to[0] - at[0], to[1] - at[1])) % 360.0


def landmark_bearing_deg(landmark: Landmark, at: tuple[float, float]) -> float:
    """Heading from `at` to the landmark: the circular mean over its points."""
    return _circular_mean([bearing_deg(at, point) for point in landmark.points]) % 360.0


def in_view(mask: np.ndarray, cells: Cells, at: tuple[float, float]) -> bool:
    """Whether the cell holding `at` sees the landmark; False outside the cells."""
    col = math.floor((at[0] - cells.left) / cells.res)
    row = math.floor((cells.top - at[1]) / cells.res)
    return 0 <= row < cells.shape[0] and 0 <= col < cells.shape[1] and bool(mask[row, col])


def landmark_view(
    landmarks: list[Landmark], masks: dict[str, np.ndarray], cells: Cells, at: tuple[float, float]
) -> list[dict]:
    """The landmarks seen from `at`, with the heading to each."""
    return [
        {
            "id": landmark.id,
            "title": landmark.title,
            "heading_deg": round(landmark_bearing_deg(landmark, at), 1),
        }
        for landmark in landmarks
        if in_view(masks[landmark.id], cells, at)
    ]


def leg_directions(
    path: list[dict],
    legs: list[dict],
    landmarks: list[Landmark],
    masks: dict[str, np.ndarray],
    cells: Cells,
    *,
    step_m: float,
) -> list[dict]:
    """One direction per leg of a route (path points and legs as in the route response)."""
    points = [(float(p["x"]), float(p["y"])) for p in path]
    out = []
    for number, leg in enumerate(legs):
        start, end = leg["start_index"], leg["end_index"]
        samples = _samples(points[start : end + 1], step_m)
        seen = []
        for landmark in landmarks:
            relative = [
                _wrap(landmark_bearing_deg(landmark, at) - heading)
                for at, heading in samples
                if in_view(masks[landmark.id], cells, at)
            ]
            mean = _wrap(_circular_mean(relative)) if relative else None
            seen.append(
                {
                    "id": landmark.id,
                    "share_of_leg_in_view": round(len(relative) / len(samples), 3),
                    "relative_deg": None if mean is None else round(mean, 1),
                    "side": None if mean is None else _side(mean),
                }
            )
        chosen = next(
            (
                (landmark, view)
                for landmark, view in zip(landmarks, seen, strict=True)
                if view["share_of_leg_in_view"] >= MIN_SHARE_IN_VIEW
            ),
            None,
        )
        out.append(
            {
                "leg": number,
                "start_index": start,
                "end_index": end,
                "heading_deg": round(bearing_deg(points[start], points[end]), 1),
                "landmark": chosen[0].id if chosen else None,
                "side": chosen[1]["side"] if chosen else None,
                "text": _text(chosen[0], chosen[1]["side"]) if chosen else None,
                "landmarks": seen,
            }
        )
    return out


def _samples(
    points: list[tuple[float, float]], step_m: float
) -> list[tuple[tuple[float, float], float]]:
    """Positions every step_m along the path (at the middle of each step), each with the
    heading of the segment it lies on."""
    samples = []
    for a, b in zip(points, points[1:], strict=False):
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        if length == 0:
            continue
        heading = bearing_deg(a, b)
        n = max(1, math.ceil(length / step_m))
        for k in range(n):
            t = (k + 0.5) / n
            samples.append(((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])), heading))
    if not samples:
        raise ValueError("a leg of no length has no heading to give directions from")
    return samples


def _side(relative_deg: float) -> str:
    if abs(relative_deg) <= AHEAD_DEG:
        return "ahead"
    if abs(relative_deg) >= BEHIND_DEG:
        return "behind"
    return "left" if relative_deg < 0 else "right"


def _text(landmark: Landmark, side: str) -> str:
    name = landmark.in_sentence or landmark.title
    if side == "ahead":
        return f"Walk towards {name}"
    if side == "behind":
        return f"Keep {name} behind you"
    return f"Keep {name} on your {side}"


def _wrap(angle_deg: float) -> float:
    """An angle in degrees, wrapped into (-180, 180]."""
    return -((-angle_deg + 180.0) % 360.0 - 180.0)


def _circular_mean(angles_deg: list[float]) -> float:
    rad = np.radians(angles_deg)
    return math.degrees(math.atan2(np.sin(rad).mean(), np.cos(rad).mean()))
