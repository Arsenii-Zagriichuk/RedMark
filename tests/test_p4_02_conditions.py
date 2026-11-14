"""P4-02: Tests for the Mars24 sun-position module and conditions generator.

Independent reference values:
  - Landing JD: 2012-08-06 05:17:57 UTC = JD 2456145.72079, computed from
    the known JD 2455927.5 = 2012-01-01 00:00 UTC and a day count.
  - Analytical limits: δ_s = 0° at Ls = 0°; δ_s = 25.44° at Ls = 90°.
  - Geometric noon elevation: 90° − |δ − φ|  (cross-checks the spherical trig).
  - Equinox equator sunset: LTST 18:00 exactly.
"""

import json
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
    assert result["provenance"]["script"] != "stub"
    assert len(result["provenance"]["inputs"]) >= 1, "expected at least one PDS input"


def test_dust_estimated():
    from conditions.gen_conditions import gen_conditions

    result = gen_conditions(sol=_SOL)
    assert result["dust"]["source"] == "estimated"
