"""Generate conditions/<sol>.json for a Curiosity sol at Gale Crater.

Run:  uv run python -m conditions.gen_conditions

Sources:
  Sun position       – Mars24 algorithm (Allison & McEwen 2000)
  Radiation           – typical RAD value for non-storm sols (Hassler et al. 2014)
  Temperature/pressure – sinusoidal REMS seasonal model for Gale (Martínez et al. 2017)
  Dust                – seasonal estimate (PDS opacity bundle ends at sol 3902)
"""

from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

from conditions.mars24 import (
    GALE_LAT_DEG,
    equation_of_center_deg,
    equation_of_time_deg,
    jde_from_msd,
    mars_mean_anomaly_deg,
    msd_for_sol,
    solar_longitude_deg,
    sun_position,
    sunset_lmst,
)

SOL = 4600
SITE = "gale"


def gen_conditions(sol: int = SOL) -> dict:
    """Return a conditions dict that validates against conditions.json schema."""
    msd = msd_for_sol(sol)
    jde = jde_from_msd(msd)

    ls = solar_longitude_deg(jde)
    m_deg = mars_mean_anomaly_deg(jde)
    eoc = equation_of_center_deg(m_deg)
    eot = equation_of_time_deg(ls, eoc)

    ss = sunset_lmst(ls, eot, GALE_LAT_DEG)

    steps = []
    for lmst_h in range(6, 21):
        az, el = sun_position(float(lmst_h), ls, eot, GALE_LAT_DEG)

        # Sinusoidal REMS temperature model: min ≈ −70 °C at 05:00, max ≈ −5 °C at 14:00
        temp_c = -37.5 + 32.5 * math.cos(math.radians((lmst_h - 14.0) * 15.0))

        # Diurnal pressure model: mean ≈ 830 Pa, amplitude ≈ 20 Pa, min at ~16:00
        pressure_pa = 830.0 + 20.0 * math.cos(math.radians((lmst_h - 4.0) * 15.0))

        steps.append(
            {
                "lmst": f"{lmst_h:02d}:00",
                "temperature_c": round(temp_c, 1),
                "pressure_pa": round(pressure_pa, 1),
                "sun_azimuth_deg": round(az % 360.0, 2),
                "sun_elevation_deg": round(el, 2),
            }
        )

    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        commit = ""

    return {
        "site": SITE,
        "sol": sol,
        "radiation_ugy_per_day": 232.0,
        "dust": {"optical_depth": 0.50, "source": "estimated"},
        "sunset_lmst": ss,
        "steps": steps,
        "provenance": {
            "script": "conditions/gen_conditions.py",
            "commit": commit,
            "inputs": [],
        },
    }


def main() -> None:
    result = gen_conditions()
    out = Path(__file__).parent / f"{SOL}.json"
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Wrote {out} (Ls={solar_longitude_deg(jde_from_msd(msd_for_sol(SOL))):.1f}°)")


if __name__ == "__main__":
    main()
