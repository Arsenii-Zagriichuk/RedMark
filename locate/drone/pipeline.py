"""One Navcam frame to a drone fix: where to search, then straighten, cut, match.

The search is centred on the previous photo's fix, moved by however far the
drone thinks it flew since that photo: its onboard track drifts over a flight,
but not much between two frames. The first fix of a flight has no previous
photo, so it starts from the onboard position alone.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from locate.drone.fix import DroneFix, GroundView, MapWindow, Matcher, locate_on_map
from locate.drone.ground import HALF_SIZE_M, read_map_window, straighten
from locate.drone.label import DroneFrame

RESOLUTION = 0.25  # the photo map's scale, metres per pixel
# How far from the search centre the search reaches, metres. Ingenuity's track
# can be about 20 m off; the window is wider to leave room.
SEARCH_RADIUS_M = 60.0


@dataclass(frozen=True)
class PreviousPhoto:
    fix: tuple[float, float]  # its drone fix, map metres
    onboard: tuple[float, float]  # the onboard position when it was taken


def search_centre(
    onboard: tuple[float, float], previous: PreviousPhoto | None
) -> tuple[float, float]:
    """Map metres to centre the search on, for a photo at `onboard`."""
    if previous is None:
        return onboard
    return (
        previous.fix[0] + onboard[0] - previous.onboard[0],
        previous.fix[1] + onboard[1] - previous.onboard[1],
    )


def fix_frame(
    raw: np.ndarray,
    frame: DroneFrame,
    crop: Path,
    centre: tuple[float, float],
    matcher: Matcher,
) -> tuple[GroundView, MapWindow, DroneFix]:
    """Straighten `raw`, cut the map window around `centre` from `crop`, and fix."""
    ground = straighten(raw, frame, RESOLUTION)
    window = read_map_window(crop, centre, SEARCH_RADIUS_M + HALF_SIZE_M)
    return ground, window, locate_on_map(ground, window, matcher)
