"""Generate conditions/<sol>.json for a Curiosity sol at Gale Crater.

Run:  uv run python -m conditions.gen_conditions

Sources:
  Sun position        – Mars24 algorithm (Allison & McEwen 2000)
  Radiation           – RAD RDR from PDS, else typical value (Hassler et al. 2014)
  Temperature/pressure – REMS MODRDR from PDS, else sinusoidal seasonal model
  Dust                – seasonal estimate (PDS opacity bundle ends at sol 3902)
"""

from __future__ import annotations

import csv
import hashlib
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
from contracts.paths import STUB_DATA, data_root

SOL = 4600
SITE = "gale"

# Default values when PDS files are not available.
_DEFAULT_RAD_UGY = 232.0  # typical non-storm dose, Hassler et al. 2014
_DEFAULT_DUST_TAU = 0.50  # typical northern-summer opacity at Gale


# ---------------------------------------------------------------------------
# PDS readers — return (value, provenance_input | None)
# ---------------------------------------------------------------------------

ProvenanceInput = dict  # {"path": str, "sha256": str}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_rad(sol: int) -> tuple[float, ProvenanceInput | None]:
    """Try to read daily dose from a RAD RDR CSV under REDMARK_DATA/rad/."""
    rad_dir = data_root() / "rad"
    if not rad_dir.is_dir():
        return _DEFAULT_RAD_UGY, None
    for csv_path in sorted(rad_dir.glob("*.csv")):
        try:
            with csv_path.open(newline="") as f:
                for row in csv.DictReader(f):
                    if int(row.get("SOL", -1)) == sol:
                        dose = float(row["DOSE_RATE_UGY_PER_DAY"])
                        return dose, {"path": str(csv_path), "sha256": _sha256(csv_path)}
        except (KeyError, ValueError):
            continue
    return _DEFAULT_RAD_UGY, None


def _read_rems(sol: int) -> tuple[list[tuple[int, float, float]], ProvenanceInput | None]:
    """Try to read hourly (lmst_h, temp_c, pressure_pa) from REMS MODRDR CSV.

    Returns (list_of_tuples, provenance_input | None).  An empty list means
    "use the fallback model".
    """
    rems_dir = data_root() / "rems"
    if not rems_dir.is_dir():
        return [], None
    for csv_path in sorted(rems_dir.glob("*.csv")):
        try:
            rows: list[tuple[int, float, float]] = []
            with csv_path.open(newline="") as f:
                for row in csv.DictReader(f):
                    if int(row.get("SOL", -1)) == sol:
                        lmst_h = int(row["LMST_HOUR"])
                        temp = float(row["TEMPERATURE_C"])
                        pres = float(row["PRESSURE_PA"])
                        rows.append((lmst_h, temp, pres))
            if rows:
                return rows, {"path": str(csv_path), "sha256": _sha256(csv_path)}
        except (KeyError, ValueError):
            continue
    return [], None


def _model_temp_c(lmst_h: float) -> float:
    """Sinusoidal REMS model: min ≈ −70 °C at 05:00, max ≈ −5 °C at 14:00."""
    return -37.5 + 32.5 * math.cos(math.radians((lmst_h - 14.0) * 15.0))


def _model_pressure_pa(lmst_h: float) -> float:
    """Diurnal pressure model: mean ≈ 830 Pa, amplitude ≈ 20 Pa."""
    return 830.0 + 20.0 * math.cos(math.radians((lmst_h - 4.0) * 15.0))


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------


def gen_conditions(sol: int = SOL) -> dict:
    """Return a conditions dict that validates against conditions.json schema."""
    msd = msd_for_sol(sol)
    jde = jde_from_msd(msd)

    ls = solar_longitude_deg(jde)
    m_deg = mars_mean_anomaly_deg(jde)
    eoc = equation_of_center_deg(m_deg)
    eot = equation_of_time_deg(ls, eoc)

    ss = sunset_lmst(ls, eot, GALE_LAT_DEG)

    # Read PDS data if available, else fall back to models / defaults.
    rad_ugy, rad_prov = _read_rad(sol)
    rems_rows, rems_prov = _read_rems(sol)
    rems_by_hour = {h: (t, p) for h, t, p in rems_rows}

    emitted_hours = range(6, 21)
    used_model = False
    steps = []
    for lmst_h in emitted_hours:
        az, el = sun_position(float(lmst_h), ls, eot, GALE_LAT_DEG)

        if lmst_h in rems_by_hour:
            temp_c, pressure_pa = rems_by_hour[lmst_h]
        else:
            temp_c = _model_temp_c(lmst_h)
            pressure_pa = _model_pressure_pa(lmst_h)
            used_model = True

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

    inputs = [p for p in (rad_prov, rems_prov) if p is not None]

    # Mark as stub (AGENTS rule 5) when:
    #   - data comes from the bundled stub-data fixtures, OR
    #   - any required measurement is missing (no RAD/REMS file found), OR
    #   - REMS coverage is incomplete (model filled in for some hours).
    from_stubs = data_root().resolve() == STUB_DATA.resolve()
    has_all_inputs = rad_prov is not None and rems_prov is not None and not used_model
    script = "stub" if from_stubs or not has_all_inputs else "conditions/gen_conditions.py"

    return {
        "site": SITE,
        "sol": sol,
        "radiation_ugy_per_day": rad_ugy,
        "dust": {"optical_depth": _DEFAULT_DUST_TAU, "source": "estimated"},
        "sunset_lmst": ss,
        "steps": steps,
        "provenance": {
            "script": script,
            "commit": commit,
            "inputs": inputs,
        },
    }


def main() -> None:
    result = gen_conditions()
    out = Path(__file__).parent / f"{SOL}.json"
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Wrote {out} (Ls={solar_longitude_deg(jde_from_msd(msd_for_sol(SOL))):.1f}°)")


if __name__ == "__main__":
    main()
