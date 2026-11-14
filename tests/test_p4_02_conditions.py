"""P4-02: Tests for the Mars24 sun-position module and conditions generator.

Independent reference values come from:
  - Analytical limits: δ_s = 0° at Ls = 0° (equinox), δ_s ≈ 25.44° at Ls = 90°.
  - Geometric noon elevation: 90° − |δ_s − φ| (different formula from the
    code's full spherical trig, so it cross-checks the computation).
  - Sunset hour angle: cos H = −tan δ_s · tan φ  (textbook formula).
"""

import json
from pathlib import Path

import jsonschema

from conditions.mars24 import (
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

# Mars obliquity = 25.19°.  At Ls = 90° the exact declination is
#   arcsin(sin 25.19°) + 0.25·sin 90° = 25.19° + 0.25° = 25.44°.
# At Ls = 0° the exact declination is 0°.
_OBLIQUITY = 25.19
_DECL_AT_LS90 = _OBLIQUITY + 0.25  # 25.44°


# ---------------------------------------------------------------------------
# Solar declination at analytical limits (independent of the code's formula)
# ---------------------------------------------------------------------------


def test_declination_zero_at_equinox():
    """At Ls = 0° (equinox), declination must be 0°."""
    assert abs(solar_declination_deg(0.0)) < 0.01


def test_declination_at_solstice():
    """At Ls = 90° (summer solstice), δ_s must equal obliquity + 0.25°."""
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


def test_solar_longitude_range():
    jde = jde_from_msd(msd_for_sol(_SOL))
    ls = solar_longitude_deg(jde)
    assert 90.0 <= ls <= 150.0, f"Ls = {ls:.1f}°"


# ---------------------------------------------------------------------------
# Noon elevation vs geometric formula 90° − |δ − φ|
# (this formula never appears in mars24.py; it cross-checks the spherical trig)
# ---------------------------------------------------------------------------


def _geometric_noon_elevation(ls_deg: float, lat_deg: float) -> float:
    delta = solar_declination_deg(ls_deg)
    return 90.0 - abs(delta - lat_deg)


def test_noon_elevation():
    jde = jde_from_msd(msd_for_sol(_SOL))
    ls = solar_longitude_deg(jde)
    m_deg = mars_mean_anomaly_deg(jde)
    eoc = equation_of_center_deg(m_deg)
    eot = equation_of_time_deg(ls, eoc)
    lmst_noon = 12.0 - eot * (24.0 / 360.0)
    _az, el = sun_position(lmst_noon, ls, eot, GALE_LAT_DEG)
    ref = _geometric_noon_elevation(ls, GALE_LAT_DEG)
    assert abs(el - ref) < 0.5, f"{el:.2f}° vs geometric {ref:.2f}°"
    assert 55.0 <= el <= 67.0


# ---------------------------------------------------------------------------
# At solar noon, sun is near north for Gale's southern latitude
# ---------------------------------------------------------------------------


def test_noon_azimuth_near_north():
    jde = jde_from_msd(msd_for_sol(_SOL))
    ls = solar_longitude_deg(jde)
    m_deg = mars_mean_anomaly_deg(jde)
    eoc = equation_of_center_deg(m_deg)
    eot = equation_of_time_deg(ls, eoc)
    lmst_noon = 12.0 - eot * (24.0 / 360.0)
    az, _el = sun_position(lmst_noon, ls, eot, GALE_LAT_DEG)
    from_north = min(az, 360.0 - az)
    assert from_north < 5.0, f"azimuth {az:.2f}° not near north"


# ---------------------------------------------------------------------------
# Sunset time in expected window
# ---------------------------------------------------------------------------


def test_sunset_time():
    jde = jde_from_msd(msd_for_sol(_SOL))
    ls = solar_longitude_deg(jde)
    m_deg = mars_mean_anomaly_deg(jde)
    eoc = equation_of_center_deg(m_deg)
    eot = equation_of_time_deg(ls, eoc)
    ss = sunset_lmst(ls, eot, GALE_LAT_DEG)
    h, m = map(int, ss.split(":"))
    total = h * 60 + m
    assert 17 * 60 <= total <= 18 * 60 + 10, f"sunset {ss}"


# ---------------------------------------------------------------------------
# Sun below horizon at midnight
# ---------------------------------------------------------------------------


def test_sun_below_horizon_at_midnight():
    jde = jde_from_msd(msd_for_sol(_SOL))
    ls = solar_longitude_deg(jde)
    m_deg = mars_mean_anomaly_deg(jde)
    eoc = equation_of_center_deg(m_deg)
    eot = equation_of_time_deg(ls, eoc)
    _az, el = sun_position(0.0, ls, eot, GALE_LAT_DEG)
    assert el < 0.0


# ---------------------------------------------------------------------------
# Equinox sunset at equator is exactly 18:00 LTST (independent analytical)
# ---------------------------------------------------------------------------


def test_equinox_sunset_at_equator():
    """At Ls = 0° and lat = 0°, sunset hour angle = 90° → LTST 18:00."""
    eot_at_equinox = equation_of_time_deg(0.0, 0.0)
    ss = sunset_lmst(0.0, eot_at_equinox, 0.0)
    h, m = map(int, ss.split(":"))
    total = h * 60 + m
    assert abs(total - 18 * 60) <= 2, f"equinox equator sunset {ss}, expected ~18:00"


# ---------------------------------------------------------------------------
# Generated conditions file validates against the schema
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


# ---------------------------------------------------------------------------
# Provenance is not stub
# ---------------------------------------------------------------------------


def test_provenance_not_stub():
    from conditions.gen_conditions import gen_conditions

    result = gen_conditions(sol=_SOL)
    assert result["provenance"]["script"] != "stub"
    assert result["provenance"]["script"] != ""


# ---------------------------------------------------------------------------
# Dust is labelled estimated
# ---------------------------------------------------------------------------


def test_dust_estimated():
    from conditions.gen_conditions import gen_conditions

    result = gen_conditions(sol=_SOL)
    assert result["dust"]["source"] == "estimated"
