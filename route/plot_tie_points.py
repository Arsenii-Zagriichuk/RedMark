from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import rasterio
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from PIL import Image, ImageDraw
from rasterio.transform import from_origin

from contracts.paths import REPO_ROOT
from prep.jezero.site_frame import SITE_PROJ
from route.answer_key import KeyFrame, draw_overlay
from route.tie_points import fit_tie_points


def main() -> None:
    photo_points = np.array([[10, 10], [110, 10], [110, 90], [10, 90]])
    map_points = np.array(
        [[4354020, 1092220], [4354020, 1092020], [4353860, 1092020], [4353860, 1092220]]
    )
    image = Image.fromarray(
        np.random.default_rng(23).integers(70, 150, size=(101, 121), dtype=np.uint8)
    )
    draw = ImageDraw.Draw(image)
    for x, y, radius in ((10, 10, 4), (110, 10, 6), (110, 90, 8), (10, 90, 3), (60, 50, 10)):
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius), fill=210, outline=20, width=2
        )
    draw.line([(20, 30), (95, 35), (50, 80)], fill=30, width=3)
    photo = np.asarray(image)
    base = np.full((181, 161), 110, dtype=np.uint8)
    base[30:151, 20:121] = np.rot90(photo, k=3)
    with TemporaryDirectory() as directory:
        root = Path(directory)
        crop = root / "synthetic-map.tif"
        with rasterio.open(
            crop,
            "w",
            driver="GTiff",
            width=161,
            height=181,
            count=1,
            dtype="uint8",
            crs=SITE_PROJ,
            transform=from_origin(4353799, 1092301, 2, 2),
        ) as output:
            output.write(base, 1)
        frame = KeyFrame(
            photo_id="p4-01-generated-example",
            flight=9,
            projection=SITE_PROJ,
            image=photo,
            valid=np.ones(photo.shape, dtype=bool),
            reference_px=(60, 50),
            heading_deg=0,
            crop=crop,
            inputs=(),
        )
        fit = fit_tie_points(photo_points, map_points, frame.reference_px, frame.heading_deg)
        figure = Figure(figsize=(15, 5), layout="constrained")
        FigureCanvasAgg(figure)
        draw_overlay(figure, frame, photo_points, map_points, fit, simulated=True)
        folder = REPO_ROOT / "route" / "overlays"
        folder.mkdir(parents=True, exist_ok=True)
        figure.savefig(folder / "p4-01-tie-points.png", dpi=120)


if __name__ == "__main__":
    main()
