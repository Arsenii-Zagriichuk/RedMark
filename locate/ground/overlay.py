"""Overlay images for the ground match: the overhead view beside the photo-map
window it was searched in, with the fix (where the view landed) and the true
position (PLACES) drawn on the map."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from locate.ground.match import GroundMatch  # noqa: E402
from locate.ground.pile import PileStop  # noqa: E402

ERROR_OK_M = 5.0


Row = tuple[PileStop, GroundMatch, float, float]


def draw_matches(path: Path, title: str, rows: list[Row]) -> None:
    """One row per stop: (stop, match, true x, true y)."""
    fig, axes = plt.subplots(len(rows), 2, figsize=(6.4, 3.0 * len(rows)), squeeze=False)
    for (stop, match, true_x, true_y), (left, right) in zip(rows, axes, strict=True):
        view = np.ma.masked_array(stop.view.image, ~stop.view.mask)
        half = stop.view.size_m / 2
        left.imshow(view, cmap="gray", extent=(-half, half, -half, half))
        left.set_title(f"{stop.photo_id[:22]}\noverhead view, north up (m)", fontsize=7)
        window = stop.window
        height, width = window.image.shape
        extent = (
            window.left_x,
            window.left_x + width * 0.25,
            window.top_y - height * 0.25,
            window.top_y,
        )
        right.imshow(window.image, cmap="gray", extent=extent)
        error = float(np.hypot(match.x - true_x, match.y - true_y))
        colour = "lime" if error <= ERROR_OK_M else "red"
        right.add_patch(
            plt.Rectangle(
                (match.x - half, match.y - half), 2 * half, 2 * half, fill=False, ec=colour, lw=1.2
            )
        )
        right.plot(match.x, match.y, "+", color=colour, ms=10, mew=2)
        right.plot(true_x, true_y, "mx", ms=8, mew=2)
        right.set_title(
            f"photo map: fix {error:.1f} m from PLACES (x)\n"
            f"peak {match.peak:.2f}, runner-up {match.runner_up:.2f}",
            fontsize=7,
        )
        for ax in (left, right):
            ax.tick_params(labelsize=5)
    fig.suptitle(title, fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 1 - 0.3 / fig.get_figheight()))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=80)
    plt.close(fig)
