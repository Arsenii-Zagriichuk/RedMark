"""The Jezero site frame: map metres that are ground metres at Jezero.

The published HiRISE photo map is equirectangular with true scale at the
equator, so at Jezero (about 18.4°N) its east–west metres are about 5% too
long. The site frame keeps the same sphere and origin but puts true scale at
18.4663°N, the standard parallel NASA's own Ingenuity waypoints use, so a
position here equals NASA's published Easting and Northing.
"""

from pyproj import Transformer

SITE_LAT_TS = 18.4663
SITE_PROJ = f"+proj=eqc +lat_ts={SITE_LAT_TS} +lon_0=0 +R=3396190 +units=m +no_defs"
SOURCE_PROJ = "+proj=eqc +lat_ts=0 +lon_0=0 +R=3396190 +units=m +no_defs"
LONLAT_PROJ = "+proj=longlat +R=3396190 +no_defs"

_TO_SITE = Transformer.from_crs(LONLAT_PROJ, SITE_PROJ, always_xy=True)


def to_site_frame(lon: float, lat: float) -> tuple[float, float]:
    """East longitude and latitude in degrees to site-frame metres (x, y)."""
    x, y = _TO_SITE.transform(lon, lat)
    return float(x), float(y)
