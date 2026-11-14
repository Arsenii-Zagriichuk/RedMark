"""Readers for the archived RAD RDR and REMS MODRDR6 products."""

import csv
import math
from collections import defaultdict
from pathlib import Path
from statistics import fmean


def read_rad_rdr(path: Path, sol: int) -> float | None:
    """Duration-weighted RAD E dose rate, converted from uGy/hour to uGy/24h.

    RAD_RDR_SIS section 4.2.1.6 defines the dose units. Detector E is the
    tissue-equivalent plastic detector, not silicon detector B. Bad-QC and
    dosimetry-free observations do not contribute.
    """
    file_sol = None
    observation_sol = None
    duration = 0.0
    quality = ""
    pending_dose = False
    weighted_dose = exposure = 0.0
    with path.open(encoding="ascii") as source:
        for raw in source:
            line = raw.strip()
            if line.startswith("[OBSERVATION:"):
                observation_sol, duration, quality = None, 0.0, ""
                pending_dose = False
            elif line.startswith("START_SOL="):
                file_sol = int(line.partition("=")[2])
            elif line.startswith("START_OBS_MARS="):
                observation_sol = int(line.partition("=")[2].strip('"').split()[0])
            elif line.startswith("OBS_DURATION="):
                duration = float(line.partition("=")[2])
            elif line.startswith("QC="):
                quality = line.partition("=")[2].strip('"')
            elif line.startswith("[DOSIMETRY_TOTAL_DOSE_E:"):
                pending_dose = True
            elif pending_dose and line:
                pending_dose = False
                dose = float(line)
                if (
                    observation_sol == sol
                    and quality == "00000000"
                    and duration > 0
                    and math.isfinite(dose)
                    and dose >= 0
                ):
                    weighted_dose += dose * duration
                    exposure += duration
    if file_sol != sol or not exposure:
        return None
    return weighted_dose / exposure * 24.0


def read_rems_modrdr(path: Path, sol: int) -> list[tuple[int, float, float]]:
    """Mean valid ambient temperature and pressure within each LMST hour.

    MODRDR6.FMT columns 2/16/17/38/40 define LMST, ambient Kelvin, temperature
    confidence, pressure Pa, and pressure confidence. Temperature must be
    reliable and within its operational error range; pressure must be free
    of the shadow effect. -999 missing values never enter the hourly mean.
    """
    hourly: dict[int, list[tuple[float, float]]] = defaultdict(list)
    with path.open(encoding="ascii", newline="") as source:
        for row in csv.reader(source):
            if len(row) != 40:
                continue
            stamp = row[1].strip()
            if not stamp.startswith(f"{sol:05d}M"):
                continue
            try:
                hour = int(stamp[6:8])
                kelvin, pressure = float(row[15]), float(row[37])
            except ValueError:
                continue
            if (
                0 <= hour <= 23
                and math.isfinite(kelvin)
                and math.isfinite(pressure)
                and kelvin > 0
                and pressure > 0
                and row[16].strip().endswith("11")
                and row[39].strip().endswith("1")
            ):
                hourly[hour].append((kelvin, pressure))
    return [
        (hour, fmean(t for t, _ in values) - 273.15, fmean(p for _, p in values))
        for hour, values in sorted(hourly.items())
    ]
