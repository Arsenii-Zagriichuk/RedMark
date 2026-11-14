"""Stage 2's result for the simulation and the app (P3-08).

The attempt (P3-07) was a no-go, so stage 2 is simulated: an error model from JPL's
published results for the same method, not from our own measurements.

`uv run python -m locate.ground.stage2_result` writes results/ground/ground-gale.json
(`simulated: true`), which the walk simulation reads for its ground fix size, and a chart
of the model against the attempt's measured errors to locate/ground/overlays/.
"""

import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from contracts.models.common import Point, Provenance, TerrainType  # noqa: E402
from contracts.models.fix_result import FixResult  # noqa: E402
from contracts.models.test_summary import TestSummary  # noqa: E402
from contracts.paths import REPO_ROOT  # noqa: E402
from contracts.scoring import score_fix, write_test_summary  # noqa: E402

TEST = "ground-gale"
SCRIPT = Path(__file__)
# The attempt's fixes on the 40 held-out stops (P3-07), each scored against PLACES.
MEASURED_FIXES = REPO_ROOT / "results" / "ground" / "fixes"
OVERLAY = REPO_ROOT / "locate" / "ground" / "overlays" / "p3-08-stage-2-model.png"
GOLDEN_ANGLE_DEG = 180.0 * (3.0 - math.sqrt(5.0))

# Nash et al., "Censible: A Robust and Practical Global Localization Framework for
# Planetary Surface Missions", ICRA 2024, Table I: Perseverance Navcam panoramas
# matched to the HiRISE map, scored against hand-aligned orthomosaics.
# https://www-robotics.jpl.nasa.gov/media/documents/2024_Global_Localization_ICRA.pdf
PUBLISHED_LOCATIONS = 264
PUBLISHED_AVERAGE_ERROR_M = 0.36
PUBLISHED_99TH_PERCENTILE_M = 0.93
PUBLISHED_MAX_ERROR_M = 1.07
# Table IV: five stereo pairs at 2560 x 1920 on flight-identical hardware.
PUBLISHED_TIME_PER_FIX_S = 81.0


@dataclass(frozen=True)
class ErrorModel:
    """A 2D normal position error, the same sigma on each axis."""

    sigma_m: float

    def radius_at_m(self, share: float) -> float:
        """The radius that `share` (0 to 1) of fixes fall within."""
        return self.sigma_m * math.sqrt(-2.0 * math.log(1.0 - share))

    @property
    def median_m(self) -> float:
        return self.radius_at_m(0.5)

    @property
    def circle_95_m(self) -> float:
        return self.radius_at_m(0.95)


def error_model() -> ErrorModel:
    """Sigma from the published average radial error: a 2D normal's is sigma * sqrt(pi / 2)."""
    return ErrorModel(sigma_m=PUBLISHED_AVERAGE_ERROR_M / math.sqrt(math.pi / 2.0))


def write_stage2_result(
    measured_fixes: Path = MEASURED_FIXES, results_dir: Path = REPO_ROOT / "results"
) -> Path:
    """The model's fixes at the attempt's held-out stops, scored into ground-gale.json.

    Only each stop's true position, heading and terrain type are used; the attempt's own
    errors are not. Within each terrain group the stops take the model's error at evenly
    spaced shares ((i + 0.5) / n), so the summary shows the model, not one random draw.
    """
    paths = sorted(measured_fixes.glob("*.json"))
    stops = [FixResult.model_validate_json(path.read_text()) for path in paths]
    if not stops or any(stop.simulated or stop.truth is None for stop in stops):
        raise ValueError(f"{measured_fixes} needs the attempt's measured, scored fixes")
    model = error_model()
    simulated = []
    for terrain in TerrainType:
        group = sorted((s for s in stops if s.terrain_type == terrain), key=lambda s: s.photo_id)
        for i, stop in enumerate(group):
            radius_m = model.radius_at_m((i + 0.5) / len(group))
            simulated.append(_simulated_fix(stop, radius_m, model, i))
    return write_test_summary(
        simulated, test=TEST, script=SCRIPT, inputs=paths, results_dir=results_dir
    )


def _simulated_fix(stop: FixResult, radius_m: float, model: ErrorModel, i: int) -> FixResult:
    # Directions turn by the golden angle, so no two errors point the same way.
    direction = math.radians(i * GOLDEN_ANGLE_DEG)
    truth = stop.truth.position
    fix = stop.model_copy(
        update={
            "position": Point(
                x=truth.x + radius_m * math.sin(direction),
                y=truth.y + radius_m * math.cos(direction),
            ),
            # Stage 2 gives position only; the fix keeps the heading it was given.
            "heading_deg": stop.truth.heading_deg,
            "uncertainty_m": model.circle_95_m,
            "confidence_pct": 95.0,
            "time_per_fix_s": PUBLISHED_TIME_PER_FIX_S,
            "simulated": True,
            "overlay": OVERLAY.relative_to(REPO_ROOT).as_posix(),
            "truth": None,
            "provenance": Provenance(
                script=SCRIPT.relative_to(REPO_ROOT).as_posix(), commit="", inputs=[]
            ),
        }
    )
    return score_fix(fix, truth, stop.truth.heading_deg)


def draw_model(measured: list[float], summary: TestSummary, out: Path = OVERLAY) -> None:
    """Share of fixes within each error: the attempt's measured fixes against the model."""
    model = error_model()
    shares = np.linspace(0.0, 0.9999, 400)
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    ax.plot(
        [model.radius_at_m(s) for s in shares],
        100 * shares,
        c="tab:blue",
        label=f"stage 2 as simulated: JPL's model, median {summary.overall.median_error_m:.2f} m",
    )
    ax.step(
        sorted(measured),
        100 * np.arange(1, len(measured) + 1) / len(measured),
        where="post",
        c="tab:red",
        label=f"P3-07 attempt, {len(measured)} held-out Gale stops (measured)",
    )
    ax.plot(
        [PUBLISHED_99TH_PERCENTILE_M, PUBLISHED_MAX_ERROR_M],
        [99, 100],
        "ko",
        label=f"JPL published, {PUBLISHED_LOCATIONS} Perseverance stops (99th pct, max)",
    )
    ax.axvline(5.0, c="grey", ls="--", label="5 m")
    ax.set_xscale("log")
    ax.set_xlim(0.05, 100)
    ax.set_ylim(0, 101)
    ax.set_xlabel("position error, ground metres")
    ax.set_ylabel("share of fixes within, %")
    ax.set_title("P3-08 stage 2 result: SIMULATED from JPL's published errors")
    ax.legend(loc="lower right", fontsize=8)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)


def main() -> None:
    path = write_stage2_result()
    summary = TestSummary.model_validate_json(path.read_text())
    measured = [
        FixResult.model_validate_json(p.read_text()).truth.position_error_m
        for p in sorted(MEASURED_FIXES.glob("*.json"))
    ]
    draw_model(measured, summary)
    o = summary.overall
    print(f"wrote {path.relative_to(REPO_ROOT)} (simulated: {str(summary.simulated).lower()})")
    print(
        f"{o.n} stops: median {o.median_error_m} m, {o.within_1m_pct:.0f}% within 1 m, "
        f"95% circle {error_model().circle_95_m:.2f} m"
    )
    print(f"wrote {OVERLAY.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
