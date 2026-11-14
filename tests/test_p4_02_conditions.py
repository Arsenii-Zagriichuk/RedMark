"""P4-02: Tests for the Mars24 sun-position module and conditions generator.

Independent reference values:
  - Landing JD: 2012-08-06 05:17:57 UTC = JD 2456145.72079, computed from
    the known JD 2455927.5 = 2012-01-01 00:00 UTC and a day count.
  - Analytical limits: δ_s = 0° at Ls = 0°; δ_s = 25.44° at Ls = 90°.
  - Geometric noon elevation: 90° − |δ − φ|  (cross-checks the spherical trig).
  - Equinox equator sunset: LTST 18:00 exactly.
  - Worked Mars24 for sol 4600: Ls ≈ 110.95°, sunset LMST 17:30,
    noon elevation ≈ 60.9°, noon azimuth ≈ 0° (north).
"""

import json
import math
from pathlib import Path

import jsonschema
import pytest

from conditions.mars24 import (
    _LANDING_JD_UTC,
    GALE_LAT_DEG,
    equation_of_center_deg,
    equation_of_time_deg,
    jde_from_msd,
    mars_mean_anomaly_deg,
    msd_for_sol,
    solar_declination_deg,
    solar_longitude_deg,
    sun_position,
    sunset_lmst,
)

_SOL = 4600

# Mars obliquity = 25.19°.  Exact declination at Ls = 90° is 25.19 + 0.25 = 25.44°.
_DECL_AT_LS90 = 25.19 + 0.25


# ---------------------------------------------------------------------------
# Shared fixture: orbital state for sol 4600
# ---------------------------------------------------------------------------


class _Sol4600:
    """Precomputed orbital state — avoids repeating the setup in each test."""

    def __init__(self) -> None:
        self.msd = msd_for_sol(_SOL)
        self.jde = jde_from_msd(self.msd)
        self.ls = solar_longitude_deg(self.jde)
        m_deg = mars_mean_anomaly_deg(self.jde)
        eoc = equation_of_center_deg(m_deg)
        self.eot = equation_of_time_deg(self.ls, eoc)


@pytest.fixture()
def sol4600() -> _Sol4600:
    return _Sol4600()


# ---------------------------------------------------------------------------
# Independent anchor: landing JD from calendar arithmetic
# ---------------------------------------------------------------------------


def test_landing_jd_matches_calendar():
    """2012-08-06 05:17:57 UTC = JD 2456145.72079, from JD 2455927.5 + 218 d + time."""
    # JD 2455927.5 = 2012-01-01 00:00 UTC (well-known reference).
    # Aug 6 is day-of-year 219 in a leap year, so 218 full days after Jan 1.
    expected = 2455927.5 + 218 + (5 * 3600 + 17 * 60 + 57) / 86400.0
    assert abs(_LANDING_JD_UTC - expected) < 1e-5, (
        f"landing JD {_LANDING_JD_UTC} vs calendar {expected}"
    )


# ---------------------------------------------------------------------------
# Declination at analytical limits (independent of the code's formula)
# ---------------------------------------------------------------------------


def test_declination_zero_at_equinox():
    assert abs(solar_declination_deg(0.0)) < 0.01


def test_declination_at_solstice():
    delta = solar_declination_deg(90.0)
    assert abs(delta - _DECL_AT_LS90) < 0.05, f"{delta:.3f}° vs expected {_DECL_AT_LS90}°"


# ---------------------------------------------------------------------------
# MSD / JDE round-trip
# ---------------------------------------------------------------------------


def test_msd_jde_round_trip():
    msd = msd_for_sol(_SOL)
    jde = jde_from_msd(msd)
    msd2 = (jde - 2451549.5) / 1.0274912517 + 44796.0 - 0.0009626
    assert abs(msd - msd2) < 1e-6


# ---------------------------------------------------------------------------
# Ls in northern-summer range
# ---------------------------------------------------------------------------


def test_solar_longitude_range(sol4600: _Sol4600):
    assert 90.0 <= sol4600.ls <= 150.0, f"Ls = {sol4600.ls:.1f}°"


# ---------------------------------------------------------------------------
# Noon elevation vs geometric formula 90° − |δ − φ|
# ---------------------------------------------------------------------------


def test_noon_elevation(sol4600: _Sol4600):
    lmst_noon = 12.0 - sol4600.eot * (24.0 / 360.0)
    _az, el = sun_position(lmst_noon, sol4600.ls, sol4600.eot, GALE_LAT_DEG)
    # Geometric reference (different formula from the spherical trig in sun_position)
    delta = solar_declination_deg(sol4600.ls)
    ref = 90.0 - abs(delta - GALE_LAT_DEG)
    assert abs(el - ref) < 0.5, f"{el:.2f}° vs geometric {ref:.2f}°"
    assert 55.0 <= el <= 67.0


# ---------------------------------------------------------------------------
# At solar noon, sun is near north
# ---------------------------------------------------------------------------


def test_noon_azimuth_near_north(sol4600: _Sol4600):
    lmst_noon = 12.0 - sol4600.eot * (24.0 / 360.0)
    az, _el = sun_position(lmst_noon, sol4600.ls, sol4600.eot, GALE_LAT_DEG)
    from_north = min(az, 360.0 - az)
    assert from_north < 5.0, f"azimuth {az:.2f}° not near north"


# ---------------------------------------------------------------------------
# Sunset time
# ---------------------------------------------------------------------------


def test_sunset_time(sol4600: _Sol4600):
    ss = sunset_lmst(sol4600.ls, sol4600.eot, GALE_LAT_DEG)
    h, m = map(int, ss.split(":"))
    total = h * 60 + m
    assert 17 * 60 <= total <= 18 * 60 + 10, f"sunset {ss}"


# ---------------------------------------------------------------------------
# Sun below horizon at midnight
# ---------------------------------------------------------------------------


def test_sun_below_horizon_at_midnight(sol4600: _Sol4600):
    _az, el = sun_position(0.0, sol4600.ls, sol4600.eot, GALE_LAT_DEG)
    assert el < 0.0


# ---------------------------------------------------------------------------
# Equinox equator sunset = 18:00 LTST (analytical, fully independent)
# ---------------------------------------------------------------------------


def test_equinox_sunset_at_equator():
    eot_eq = equation_of_time_deg(0.0, 0.0)
    ss = sunset_lmst(0.0, eot_eq, 0.0)
    h, m = map(int, ss.split(":"))
    assert abs(h * 60 + m - 18 * 60) <= 2, f"equinox equator sunset {ss}"


# ---------------------------------------------------------------------------
# Generated conditions validates against schema, reads PDS stubs
# ---------------------------------------------------------------------------


def test_conditions_schema():
    from conditions.gen_conditions import gen_conditions

    result = gen_conditions(sol=_SOL)
    schema_dir = Path(__file__).parent.parent / "contracts" / "schemas"
    schema = json.loads((schema_dir / "conditions.json").read_text())
    common = json.loads((schema_dir / "common.json").read_text())

    resolver = jsonschema.RefResolver(
        base_uri=(schema_dir / "conditions.json").as_uri(),
        referrer=schema,
        store={(schema_dir / "common.json").as_uri(): common},
    )
    jsonschema.validate(result, schema, resolver=resolver)


def test_provenance_records_pds_inputs():
    from conditions.gen_conditions import gen_conditions

    result = gen_conditions(sol=_SOL)
    # With stub data, script is "stub"; with real PDS data, it names the generator.
    assert result["provenance"]["script"] in ("stub", "conditions/gen_conditions.py")
    assert len(result["provenance"]["inputs"]) >= 1, "expected at least one PDS input"


def test_dust_estimated():
    from conditions.gen_conditions import gen_conditions

    result = gen_conditions(sol=_SOL)
    assert result["dust"]["source"] == "estimated"


# ---------------------------------------------------------------------------
# Worked Mars24 reference for sol 4600 (the agreed test seam)
#
# Values computed by hand from the Allison & McEwen (2000) algorithm:
#   Landing JD_UTC  = 2456145.72079
#   ΔTT             = 66.184 s  →  JDE_landing = 2456145.72156
#   MSD_landing     = (JDE-2451549.5)/1.0274912517 + 44796.0 − 0.0009626
#   MSD_4600        = MSD_landing + 4600
#   JDE_4600        = (MSD_4600 − 44796.0 + 0.0009626) * 1.0274912517 + 2451549.5
#   M               = (19.3871 + 0.52402073*(JDE−2451545.0)) mod 360
#   EoC             = 10.691*sin(M) + 0.623*sin(2M) + 0.050*sin(3M) + ...
#   α_FMS           = (270.3871 + 0.524038089*(JDE−2451545.0)) mod 360
#   Ls              = (α_FMS + EoC) mod 360  ≈ 110.95°
#   EoT             = 2.861*sin(2Ls) − 0.071*sin(4Ls) + 0.002*sin(6Ls) − EoC
#   δ               = arcsin(0.42565*sin(Ls)) + 0.25*sin(Ls) ≈ 23.66°
#   Sunset H        = arccos(−tan(δ)*tan(φ))  with φ = −5.4°
#   Sunset LTST     = 12 + H/15; LMST_set = LTST − EoT*(24/360) → "17:30"
#   Noon el         = 90 − |δ − φ| ≈ 60.94°
# ---------------------------------------------------------------------------


def test_worked_mars24_sol4600():
    """Pin sol 4600 sunset and noon sun direction to independently worked values."""
    # --- Independent re-derivation (raw math, no mars24 imports) ---
    landing_jd_utc = 2456145.5 + (5 * 3600 + 17 * 60 + 57) / 86400.0
    delta_tt = 66.184
    landing_jde = landing_jd_utc + delta_tt / 86400.0
    landing_msd = (landing_jde - 2451549.5) / 1.0274912517 + 44796.0 - 0.0009626

    msd_4600 = landing_msd + 4600
    jde_4600 = (msd_4600 - 44796.0 + 0.0009626) * 1.0274912517 + 2451549.5

    j2000 = 2451545.0
    dt = jde_4600 - j2000
    m_deg = (19.3871 + 0.52402073 * dt) % 360.0
    m_rad = math.radians(m_deg)
    eoc = (
        10.691 * math.sin(m_rad)
        + 0.623 * math.sin(2 * m_rad)
        + 0.050 * math.sin(3 * m_rad)
        + 0.005 * math.sin(4 * m_rad)
        + 0.0005 * math.sin(5 * m_rad)
    )
    alpha_fms = (270.3871 + 0.524038089 * dt) % 360.0
    ls_ref = (alpha_fms + eoc) % 360.0

    ls_rad = math.radians(ls_ref)
    eot_ref = (
        2.861 * math.sin(2 * ls_rad)
        - 0.071 * math.sin(4 * ls_rad)
        + 0.002 * math.sin(6 * ls_rad)
        - eoc
    )
    decl_ref = math.degrees(math.asin(0.42565 * math.sin(ls_rad))) + 0.25 * math.sin(ls_rad)

    phi = -5.4  # Gale Crater latitude
    cos_h = -math.tan(math.radians(decl_ref)) * math.tan(math.radians(phi))
    cos_h = max(-1.0, min(1.0, cos_h))
    h_set = math.degrees(math.acos(cos_h))
    ltst_set = 12.0 + h_set / 15.0
    lmst_set = ltst_set - eot_ref * (24.0 / 360.0)
    ref_h = int(lmst_set)
    ref_m = int((lmst_set - ref_h) * 60.0 + 0.5)
    if ref_m >= 60:
        ref_h += 1
        ref_m -= 60
    ref_sunset = f"{ref_h:02d}:{ref_m:02d}"

    noon_el_ref = 90.0 - abs(decl_ref - phi)

    # --- Pin the expected values ---
    assert abs(ls_ref - 110.95) < 0.1, f"Ls = {ls_ref:.2f}°"
    assert ref_sunset == "17:30"
    assert abs(noon_el_ref - 60.94) < 0.1, f"noon el = {noon_el_ref:.2f}°"

    # --- Compare production code against the independent values ---
    prod_ls = solar_longitude_deg(jde_from_msd(msd_for_sol(_SOL)))
    assert abs(prod_ls - ls_ref) < 0.01, f"prod Ls {prod_ls:.4f} vs ref {ls_ref:.4f}"

    prod_ss = sunset_lmst(prod_ls, eot_ref, phi)
    assert prod_ss == ref_sunset, f"prod sunset {prod_ss} vs ref {ref_sunset}"

    lmst_noon = 12.0 - eot_ref * (24.0 / 360.0)
    prod_az, prod_el = sun_position(lmst_noon, prod_ls, eot_ref, phi)
    assert abs(prod_el - noon_el_ref) < 0.5, f"prod noon el {prod_el:.2f} vs ref {noon_el_ref:.2f}"
    from_north = min(prod_az, 360.0 - prod_az)
    assert from_north < 1.0, f"noon azimuth {prod_az:.2f}° not near north"
