"""P4-02: Tests for the Mars24 sun-position module and conditions generator.

Expected values are worked independently from the code:
  Sol 4600 → Ls ≈ 113° at Gale Crater (−5.4°, 137.84° E).
  δ_s = arcsin(0.42565 · sin 113°) + 0.25 · sin 113° ≈ 23.3°
  Noon elevation  = 90° − |δ_s − φ| ≈ 61.3°
  Sunset hour angle: cos H = −tan δ_s · tan φ ≈ 0.041 → H ≈ 87.7°
"""

import json
import math
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


# ---- helpers for the independent reference --------------------------------


def _independent_noon_elevation(ls_deg: float, lat_deg: float) -> float:
    """90° − |δ_s − φ|, computed only from the declination formula."""
    delta = math.degrees(math.asin(0.42565 * math.sin(math.radians(ls_deg)))) + 0.25 * math.sin(
        math.radians(ls_deg)
    )
    return 90.0 - abs(delta - lat_deg)


# ---- MSD / JDE round-trip -------------------------------------------------


def test_msd_jde_round_trip():
    msd = msd_for_sol(_SOL)
    jde = jde_from_msd(msd)
    msd2 = (jde - 2451549.5) / 1.0274912517 + 44796.0 - 0.0009626
    assert abs(msd - msd2) < 1e-6


# ---- Ls in northern-summer range ------------------------------------------


def test_solar_longitude_range():
    jde = jde_from_msd(msd_for_sol(_SOL))
    ls = solar_longitude_deg(jde)
    assert 90.0 <= ls <= 150.0, f"Ls = {ls:.1f}°"


# ---- Solar declination matches its own formula ----------------------------


def test_solar_declination():
    jde = jde_from_msd(msd_for_sol(_SOL))
    ls = solar_longitude_deg(jde)
    delta = solar_declination_deg(ls)
    ref = math.degrees(math.asin(0.42565 * math.sin(math.radians(ls)))) + 0.25 * math.sin(
        math.radians(ls)
    )
    assert abs(delta - ref) < 0.01


# ---- Solar-noon elevation vs independent reference -----------------------


def test_noon_elevation():
    jde = jde_from_msd(msd_for_sol(_SOL))
    ls = solar_longitude_deg(jde)
    m_deg = mars_mean_anomaly_deg(jde)
    eoc = equation_of_center_deg(m_deg)
    eot = equation_of_time_deg(ls, eoc)
    lmst_noon = 12.0 - eot * (24.0 / 360.0)
    _az, el = sun_position(lmst_noon, ls, eot, GALE_LAT_DEG)
    ref = _independent_noon_elevation(ls, GALE_LAT_DEG)
    assert abs(el - ref) < 0.5, f"{el:.2f}° vs reference {ref:.2f}°"
    assert 55.0 <= el <= 67.0


# ---- At solar noon, sun is near north ------------------------------------


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


# ---- Sunset time in expected window --------------------------------------


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


# ---- Sun below horizon at midnight --------------------------------------


def test_sun_below_horizon_at_midnight():
    jde = jde_from_msd(msd_for_sol(_SOL))
    ls = solar_longitude_deg(jde)
    m_deg = mars_mean_anomaly_deg(jde)
    eoc = equation_of_center_deg(m_deg)
    eot = equation_of_time_deg(ls, eoc)
    _az, el = sun_position(0.0, ls, eot, GALE_LAT_DEG)
    assert el < 0.0


# ---- Generated file validates against the contract -----------------------


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


# ---- Provenance is not stub -----------------------------------------------


def test_provenance_not_stub():
    from conditions.gen_conditions import gen_conditions

    result = gen_conditions(sol=_SOL)
    assert result["provenance"]["script"] != "stub"
    assert result["provenance"]["script"] != ""


# ---- Dust is labelled estimated -------------------------------------------


def test_dust_estimated():
    from conditions.gen_conditions import gen_conditions

    result = gen_conditions(sol=_SOL)
    assert result["dust"]["source"] == "estimated"
