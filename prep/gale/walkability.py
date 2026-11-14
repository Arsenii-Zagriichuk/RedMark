"""Layer 2 at Gale (P2-03): where the ground is loose sand, and the boxwork ridges.

Both are written as single-band uint8 GeoTIFFs the route engine reads
(route/layers.py): 1 where the ground is sand or a ridge, 0 where it is not, 255
where it is unknown.
"""

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import reproject
from scipy import ndimage as ndi

from prep.common import Bounds, written_atomically

# Unknown in the sand and ridge rasters.
UNKNOWN = 255
# THEMIS thermal inertia (J m^-2 K^-1 s^-1/2) below which a 100 m cell counts as loose
# sand. A RedMark cutoff (agreed 14 Nov 2026), not a published one: most of Gale reads
# 250 to 410, an indurated surface mixed with loose material (Fergason et al. 2012,
# Space Sci. Rev. 170), so cells below 350 lean to the loose end. In the walk area it
# marks about a fifth of the ground: the dark sandy floor and hollows.
SAND_MAX_TI = 350

# The ridge finder, tuned by eye on three boxwork patches of the walk area (the
# overlays in prep/gale/evidence/ridges-*.png). Boxwork ridges there are 1 to 3 m
# wide round 10 to 20 m hollows.
RIDGE_RES_M = 0.5  # the photo is averaged to 50 cm first: ridges stay 2 px or wider
RIDGE_SCALES_M = (0.75, 1.25)  # half-widths of the lines looked for
RIDGE_BACKGROUND_M = 10.0  # the surroundings a pixel is set against
RIDGE_MIN_STRENGTH = 0.4
RIDGE_MIN_AREA_M2 = 8.0  # a ridge piece at least 8 m long at 1 m wide


def sand_raster(thermal_inertia, out):
    """1 where thermal inertia is below SAND_MAX_TI, 0 elsewhere, UNKNOWN where it is
    missing, on the thermal-inertia crop's own grid."""
    with rasterio.open(thermal_inertia) as src:
        ti = src.read(1, masked=True)
        profile = src.profile
    known = ~np.ma.getmaskarray(ti) & np.isfinite(ti.filled(np.nan))
    sand = np.full(ti.shape, UNKNOWN, dtype=np.uint8)
    sand[known] = (ti.filled(np.inf)[known] < SAND_MAX_TI).astype(np.uint8)
    _write_mask(sand, profile, out)
    return out


def find_ridges(image: np.ndarray, res_m: float) -> np.ndarray:
    """Where the photo shows a bright line 0.75 to 1.25 m across: a boxwork ridge's
    lit crest. True on a ridge.

    The photo is first set against its own surroundings (brightness minus the
    RIDGE_BACKGROUND_M blur, over the local spread), so a ridge reads the same in a
    bright or a dark patch. The ridge strength at each scale is the curvature across
    the line (the Hessian's most negative eigenvalue), scale-normalised; pixels over
    RIDGE_MIN_STRENGTH are ridge, then pieces smaller than RIDGE_MIN_AREA_M2 (a lone
    bright rock, a noise speck) are dropped. Pixels of value 0 are missing photo.
    """
    x = image.astype(np.float32)
    background = ndi.gaussian_filter(x, RIDGE_BACKGROUND_M / res_m)
    spread = np.sqrt(ndi.gaussian_filter((x - background) ** 2, RIDGE_BACKGROUND_M / res_m))
    z = (x - background) / (spread + 1.0)
    strength = np.zeros_like(z)
    for scale_m in RIDGE_SCALES_M:
        s = scale_m / res_m
        rr = ndi.gaussian_filter(z, s, order=(2, 0))
        cc = ndi.gaussian_filter(z, s, order=(0, 2))
        rc = ndi.gaussian_filter(z, s, order=(1, 1))
        across = (rr + cc) / 2 - np.sqrt(((rr - cc) / 2) ** 2 + rc**2)
        strength = np.maximum(strength, np.maximum(-across, 0) * s * s)
    ridges = (strength > RIDGE_MIN_STRENGTH) & (image > 0)
    pieces, count = ndi.label(ridges, structure=np.ones((3, 3)))
    sizes = ndi.sum(ridges, pieces, np.arange(count + 1)) * res_m * res_m
    keep = sizes >= RIDGE_MIN_AREA_M2
    keep[0] = False
    return keep[pieces]


def ridge_raster(photo, bounds: Bounds, zones: list[list[tuple[float, float]]], out):
    """The boxwork ridge map over `bounds` at RIDGE_RES_M, from the photo map.

    1 on a ridge inside one of the boxwork `zones` (polygons of map x, y), 0 elsewhere,
    UNKNOWN where the photo is missing. Outside the zones the finder would mark
    layered bedrock and sand ripples too, so no ridge is mapped there.
    """
    min_x, min_y, max_x, max_y = bounds
    width, height = round((max_x - min_x) / RIDGE_RES_M), round((max_y - min_y) / RIDGE_RES_M)
    transform = from_origin(min_x, max_y, RIDGE_RES_M, RIDGE_RES_M)
    image = np.zeros((height, width), dtype=np.float32)
    with rasterio.open(photo) as src:
        crs = src.crs
        reproject(
            rasterio.band(src, 1),
            image,
            src_nodata=src.nodata,
            dst_nodata=0,
            dst_transform=transform,
            dst_crs=crs,
            resampling=Resampling.average,
        )
    inside = rasterize(
        [({"type": "Polygon", "coordinates": [zone]}, 1) for zone in zones],
        out_shape=image.shape,
        transform=transform,
    ).astype(bool)
    ridges = np.where(find_ridges(image, RIDGE_RES_M) & inside, 1, 0).astype(np.uint8)
    ridges[image <= 0] = UNKNOWN
    profile = {"width": width, "height": height, "crs": crs, "transform": transform}
    profile.update(tiled=True, blockxsize=256, blockysize=256)
    _write_mask(ridges, profile, out)
    return out


def _write_mask(mask: np.ndarray, profile: dict, out) -> None:
    profile = {**profile, "driver": "GTiff", "dtype": "uint8", "nodata": UNKNOWN, "count": 1}
    profile.update(compress="deflate")
    with written_atomically(out) as part, rasterio.open(part, "w", **profile) as dst:
        dst.write(mask, 1)
