"""Overlay image of the cached break-it runs (P4-06), for checking by eye.

The uncertainty circle through each cached run in cache/demo/simulate/, with its fixes,
the fixes that could not reach the crew, and the start of lost mode. Run with
`uv run python -m sim.plot_break_it` after sim.cache_runs; the image goes to
sim/overlays/p4-06-break-it.png.
"""

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from contracts.paths import REPO_ROOT  # noqa: E402
from sim.cache_runs import OUT as CACHE  # noqa: E402
from sim.cache_runs import SCENARIOS
from sim.engine import FIX_REQUEST_OPEN_GROUND_M  # noqa: E402

OUT = REPO_ROOT / "sim" / "overlays"


def main() -> None:
    fig, ax = plt.subplots(figsize=(12, 6))
    for scenario in SCENARIOS:
        entry = json.loads((CACHE / f"walk-simulate-{scenario}.json").read_text())
        steps = entry["response"]["steps"]
        (line,) = ax.plot(
            [s["t_s"] / 60 for s in steps], [s["uncertainty_m"] for s in steps], label=scenario
        )
        for s in steps:
            for event in s["events"]:
                at = (s["t_s"] / 60, s["uncertainty_m"])
                if event["kind"] == "fix":
                    ax.plot(*at, "o", c=line.get_color(), ms=5)
                elif event["kind"] == "fix_unavailable":
                    ax.plot(*at, "x", c=line.get_color(), ms=8)
                elif event["kind"] == "lost_mode":
                    ax.annotate(
                        "lost mode",
                        at,
                        xytext=(-60, 12),
                        textcoords="offset points",
                        color=line.get_color(),
                        arrowprops={"arrowstyle": "->"},
                    )
    ax.axhline(FIX_REQUEST_OPEN_GROUND_M, c="grey", ls="--", label="fix request, open ground")
    ax.plot([], [], "ko", ms=5, label="fix")
    ax.plot([], [], "kx", ms=8, label="fix could not reach the crew")
    ax.set_xlabel("minutes into the walk")
    ax.set_ylabel("uncertainty circle, ground metres (95%)")
    ax.set_title("SIMULATED break-it runs on the stub route (seed 1); radio ranging is simulated")
    ax.legend(loc="upper left")
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "p4-06-break-it.png", dpi=110, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
