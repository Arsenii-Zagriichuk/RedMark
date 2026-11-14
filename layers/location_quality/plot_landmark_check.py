"""Check the landmark points by eye on Curiosity's own photos (P3-05).

NASA's sol 4611 Navcam mosaic (PIA26632) names Mishe Mokwa, Texoli, the upper
Mount Sharp peak and the crater rim. This draws the upper row of that mosaic's
frames (sequence NCAM00722, site 117, drive 2730) with the skyline calculated
from the rover's camera, and a line at the heading of each landmark point found
by landmarks.py, so a person can see that each line falls on the feature NASA
names. Writes layers/location_quality/overlays/p3-05-landmarks-sol4611.png.

Run with `uv run python -m layers.location_quality.plot_landmark_check`.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from contracts.paths import data_root  # noqa: E402
from layers.location_quality.landmarks import load_landmarks  # noqa: E402
from locate.horizon.fix import PLACES, read_site_config, rover_position  # noqa: E402
from locate.horizon.grid import OBSERVER_HEIGHT_M, ray_distances  # noqa: E402
from locate.horizon.navcam import pixel_headings, read_frame  # noqa: E402
from locate.horizon.render import skyline  # noqa: E402
from locate.horizon.sources import load_gale_terrain  # noqa: E402

FRAMES = [
    f"navcam/sol4611/NRB_{sclk}ILT_F1172730NCAM00722M1.LBL"
    for sclk in ("806844618", "806844774", "806844805")
]
STOP = (117, 2730)
OVERLAY = Path(__file__).parent / "overlays" / "p3-05-landmarks-sol4611.png"
COLOURS = {
    "mount_sharp_peak": "#d62728",
    "texoli": "#ff7f0e",
    "mishe_mokwa": "#e377c2",
    "crater_rim": "#17becf",
}


def main() -> None:
    site = read_site_config()
    root = data_root()
    terrain = load_gale_terrain(root, site.bounds, root / "gale" / "horizon" / "cache").terrain
    landmarks = load_landmarks(terrain, site.bounds, root / PLACES)
    frames = [read_frame(root / label) for label in FRAMES]
    rover_x, rover_y = rover_position(root / PLACES, *STOP)
    east, north = frames[0].camera_offset_m()
    cam_x, cam_y = rover_x + east, rover_y + north

    azimuths = np.arange(0.0, 360.0, 0.1)
    calculated = skyline(
        terrain,
        cam_x,
        cam_y,
        observer_height_m=OBSERVER_HEIGHT_M,
        azimuths_deg=azimuths,
        distances_m=ray_distances(5.0, 120_000.0, 1.0, 0.1),
    )
    fig, axes = plt.subplots(1, len(frames), figsize=(10 * len(frames), 11))
    for ax, frame in zip(axes, frames, strict=True):
        image = frame.image.astype(np.float64)
        low, high = np.percentile(image, [1, 99.5])
        ax.imshow(np.clip((image - low) / (high - low), 0, 1), cmap="gray")
        rows, cols = image.shape
        cc, rr = np.meshgrid(np.arange(0, cols, 4), np.arange(0, rows, 2))
        heading, elevation = pixel_headings(
            frame.camera, frame.rover_quaternion, cc.ravel(), rr.ravel()
        )
        heading, elevation = heading.reshape(cc.shape), elevation.reshape(cc.shape)
        # The calculated skyline: in each column, where the pixel elevation crosses it.
        line_x, line_y = [], []
        for j in range(cc.shape[1]):
            above = elevation[:, j] - np.interp(heading[:, j], azimuths, calculated, period=360)
            crossing = np.nonzero(np.diff(np.sign(above)))[0]
            if crossing.size:
                line_x.append(cc[0, j])
                line_y.append(rr[crossing[0], 0])
        ax.plot(line_x, line_y, "c-", lw=1, label="skyline calculated from the terrain")
        middle = heading[heading.shape[0] // 2]
        for row, landmark in enumerate(landmarks):
            for i, (x, y) in enumerate(landmark.points):
                bearing = np.degrees(np.arctan2(x - cam_x, y - cam_y)) % 360
                off = np.abs((middle - bearing + 180) % 360 - 180)
                if off.min() < 0.5:
                    col = cc[0, off.argmin()]
                    ax.axvline(col, color=COLOURS[landmark.id], lw=1.2)
                    name = landmark.title if len(landmark.points) == 1 else f"{landmark.title} {i}"
                    ax.text(
                        col + 5,
                        40 + 60 * row,
                        f"{name}\n{bearing:.0f}°",
                        color=COLOURS[landmark.id],
                    )
        for col in range(0, cols, 128):
            ax.text(col, rows - 12, f"{middle[col // 4]:.0f}°", color="yellow")
        ax.set_title(frame.photo_id)
    axes[0].legend(loc="lower left")
    fig.suptitle(
        "Landmark points found by landmarks.py, at their headings from Curiosity's Navcam on"
        " sol 4611 (NASA PIA26632 names them)"
    )
    fig.tight_layout()
    OVERLAY.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OVERLAY, dpi=60)
    print(OVERLAY)


if __name__ == "__main__":
    main()
