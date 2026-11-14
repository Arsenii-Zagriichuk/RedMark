"""Mars24 sun-position algorithm for RedMark.

Based on Allison & McEwen (2000) and the NASA GISS Mars24 sunclock.
All angles in degrees unless noted.  Pure-Python, no external dependencies.
"""

from __future__ import annotations

import math

# ---------------------------------------------------------------------------
# Gale Crater location
# ---------------------------------------------------------------------------
GALE_LAT_DEG = -5.4
GALE_LON_DEG = 137.84  # east positive

# ---------------------------------------------------------------------------
# Curiosity landing epoch
# ---------------------------------------------------------------------------
# Landing: 2012-08-06 05:17:57 UTC
# JD 2456146.5 = 2012-08-06 00:00:00 UTC (JD noon-epoch: .5 = midnight)
_LANDING_JD_UTC = 2456146.5 + (5 * 3600 + 17 * 60 + 57) / 86400.0  # 2456146.72079
# ΔTT = TT − UTC ≈ 32.184 + 34 (leap seconds in mid-2012) = 66.184 s
_DELTA_TT_2012 = 66.184
_LANDING_JDE = _LANDING_JD_UTC + _DELTA_TT_2012 / 86400.0

# MSD at landing
_LANDING_MSD = (_LANDING_JDE - 2451549.5) / 1.0274912517 + 44796.0 - 0.0009626

# J2000.0 epoch
_J2000 = 2451545.0


# ---------------------------------------------------------------------------
# Conversions
# ---------------------------------------------------------------------------


def _deg2rad(deg: float) -> float:
    return math.radians(deg)


def _rad2deg(rad: float) -> float:
    return math.degrees(rad)


def msd_for_sol(sol: int) -> float:
    """MSD at the start of a Curiosity sol (approximate: landing MSD + sol)."""
    return _LANDING_MSD + sol


def jde_from_msd(msd: float) -> float:
    """Convert Mars Sol Date → Julian Date (Terrestrial Time)."""
    return (msd - 44796.0 + 0.0009626) * 1.0274912517 + 2451549.5


def msd_from_jde(jde: float) -> float:
    """Convert JDE → Mars Sol Date."""
    return (jde - 2451549.5) / 1.0274912517 + 44796.0 - 0.0009626


# ---------------------------------------------------------------------------
# Orbital elements
# ---------------------------------------------------------------------------


def mars_mean_anomaly_deg(jde: float) -> float:
    """Mars mean anomaly M (degrees)."""
    return (19.3871 + 0.52402073 * (jde - _J2000)) % 360.0


def alpha_fms_deg(jde: float) -> float:
    """Angle of the fictitious mean sun α_FMS (degrees)."""
    return (270.3871 + 0.524038089 * (jde - _J2000)) % 360.0


def equation_of_center_deg(m_deg: float) -> float:
    """Equation of center ν − M (degrees).  PBS perturbers omitted (< 0.03°)."""
    m = _deg2rad(m_deg)
    return (
        10.691 * math.sin(m)
        + 0.623 * math.sin(2.0 * m)
        + 0.050 * math.sin(3.0 * m)
        + 0.005 * math.sin(4.0 * m)
        + 0.0005 * math.sin(5.0 * m)
    )


def solar_longitude_deg(jde: float) -> float:
    """Mars solar longitude Ls (degrees)."""
    m = mars_mean_anomaly_deg(jde)
    eoc = equation_of_center_deg(m)
    return (alpha_fms_deg(jde) + eoc) % 360.0


def solar_declination_deg(ls_deg: float) -> float:
    """Solar declination δ_s (degrees).  Mars obliquity = 25.19°."""
    ls = _deg2rad(ls_deg)
    return _rad2deg(math.asin(0.42565 * math.sin(ls))) + 0.25 * math.sin(ls)


def equation_of_time_deg(ls_deg: float, eoc_deg: float) -> float:
    """Equation of time (degrees)."""
    ls = _deg2rad(ls_deg)
    return (
        2.861 * math.sin(2.0 * ls)
        - 0.071 * math.sin(4.0 * ls)
        + 0.002 * math.sin(6.0 * ls)
        - eoc_deg
    )


# ---------------------------------------------------------------------------
# Sun position
# ---------------------------------------------------------------------------


def sun_position(
    lmst_h: float,
    ls_deg: float,
    eot_deg: float,
    lat_deg: float,
) -> tuple[float, float]:
    """Sun (azimuth_deg, elevation_deg) at a given LMST hour.

    Azimuth: 0 = north, 90 = east, 180 = south, 270 = west.
    """
    ltst_h = lmst_h + eot_deg * (24.0 / 360.0)
    H = (ltst_h - 12.0) * 15.0  # hour angle, degrees

    delta = _deg2rad(solar_declination_deg(ls_deg))
    phi = _deg2rad(lat_deg)
    H_r = _deg2rad(H)

    cos_z = math.sin(delta) * math.sin(phi) + math.cos(delta) * math.cos(phi) * math.cos(H_r)
    cos_z = max(-1.0, min(1.0, cos_z))
    z = math.acos(cos_z)
    sin_z = math.sin(z)
    elevation = 90.0 - _rad2deg(z)

    if abs(sin_z) < 1e-9:
        return 0.0, elevation

    sin_A = -math.cos(delta) * math.sin(H_r) / sin_z
    cos_A = (math.sin(delta) - cos_z * math.sin(phi)) / (sin_z * math.cos(phi))
    azimuth = _rad2deg(math.atan2(sin_A, cos_A)) % 360.0

    return azimuth, elevation


def sunset_lmst(ls_deg: float, eot_deg: float, lat_deg: float) -> str:
    """Sunset local mean solar time as HH:MM."""
    delta = _deg2rad(solar_declination_deg(ls_deg))
    phi = _deg2rad(lat_deg)

    cos_H = -math.tan(delta) * math.tan(phi)
    cos_H = max(-1.0, min(1.0, cos_H))
    H_set = _rad2deg(math.acos(cos_H))

    ltst_set = 12.0 + H_set / 15.0
    lmst_set = ltst_set - eot_deg * (24.0 / 360.0)

    h = int(lmst_set)
    m = int((lmst_set - h) * 60.0 + 0.5)
    if m >= 60:
        h += 1
        m -= 60
    return f"{h:02d}:{m:02d}"
