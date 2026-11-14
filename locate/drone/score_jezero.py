"""The drone test at Jezero (P2-06): every answer-key frame through the drone
matcher, scored through the shared scorer.

    REDMARK_DATA=~/redmark-data uv run --group gpu python -m locate.drone.score_jezero \\
        [--matcher lightglue]

Reads Person 4's answer key (P4-01, `route.answer_key.read_answer_key`) and
the Jezero pack. Each flight's keyed frames run in time order: a flight's
first frame is searched around the drone's onboard position, every later one
around the previous fix moved as the drone thinks it moved (as in
first_fix.py). A frame the matcher cannot lock on still gets a fix, at its
search centre, so a miss counts against the numbers instead of dropping out.

Flight 10 is the tuning flight: P2-05 chose the tiling and match limits on its
frames, so a key on it is refused. A key whose ground a flight 10 frame may
have seen (the flights share airfields) is left out and listed.

Writes a scored fix result per frame to results/drone/fixes/<frame>.json, its
overlay to results/drone/overlays/<frame>-<matcher>-<run-id>.png, and the test
summary results/drone/drone-jezero.json. Nothing is written unless the code
that makes the fixes is committed.
"""

import argparse
import csv
import json
import math
import os
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import numpy as np
import rasterio

from contracts.models.common import Point, Provenance, TerrainType
from contracts.models.fix_result import FixResult
from contracts.paths import REPO_ROOT, data_root
from contracts.scoring import score_fix, write_test_summary
from locate.drone.first_fix import FIX_CODE, draw_overlay, frame_onboard, label_path
from locate.drone.fix import MIN_INLIERS, Matcher, NoFix, jezero_fix_result, locate_on_map
from locate.drone.ground import HALF_SIZE_M, read_map_window, straighten
from locate.drone.label import DroneFrame, read_drone_frame
from locate.drone.matchers import load_matcher
from locate.drone.pipeline import RESOLUTION, SEARCH_RADIUS_M, PreviousPhoto, search_centre
from locate.drone.records import provenance, recorded
from prep.common import written_atomically

TEST = "drone-jezero"
# P2-05 chose the tiling and the match limits on flight 10's frame
# HNM_0152_0680432606 (and tried LightGlue on 0590), so flight 10 is tuning ground.
TUNING_FLIGHTS = frozenset({10})
# Ingenuity's own track can be about 20 m off, so a tuning frame's footprint,
# placed by its onboard position, may sit this much further over.
ONBOARD_DRIFT_M = 20.0
KEY_FRAMES_WANTED = 20  # the ticket's answer key size
# JPL's published benchmark for its map-based localisation on Ingenuity frames.
JPL_WITHIN_5M_PCT, JPL_WITHIN_10M_PCT = 89.4, 99.8


@dataclass(frozen=True)
class PackFrame:
    """What the plan needs about a frame in the Jezero pack."""

    flight: int
    sclk: float  # spacecraft clock at the exposure, seconds
    reach_m: float  # how far from the nadir its straightened view sees ground


@dataclass(frozen=True)
class Footprint:
    """The ground a tuning frame saw: a circle around its onboard position."""

    centre: tuple[float, float]
    reach_m: float


@dataclass(frozen=True)
class KeyedFrame:
    photo_id: str
    flight: int
    sclk: float
    true_position: tuple[float, float]
    true_heading_deg: float
    terrain_type: TerrainType
    hard_mode: bool


@dataclass(frozen=True)
class Plan:
    runs: list[list[KeyedFrame]]  # one per flight, in time order
    overlapping: list[str]  # keys left out: a tuning frame may have seen their ground


@dataclass(frozen=True)
class FrameInputs:
    raw: np.ndarray  # the Navcam frame, lines x samples
    camera: DroneFrame
    crop: Path  # the flight's map crop
    onboard: tuple[float, float]  # the drone's onboard position, map metres


def plan_runs(
    keys: Sequence[Mapping], pack: Mapping[str, PackFrame], tuning: Sequence[Footprint]
) -> Plan:
    """The keyed frames to run, flight by flight in time order. `keys` are
    answer-key records (route/answer_key.py); `tuning` the tuning frames' footprints."""
    kept: list[KeyedFrame] = []
    overlapping = []
    for record in keys:
        photo_id = record["photo_id"]
        if record["simulated"]:
            raise ValueError(f"{photo_id}: a simulated key is not part of the answer key")
        if photo_id not in pack:
            raise ValueError(f"{photo_id} is not a frame in the Jezero pack")
        frame = pack[photo_id]
        if record["flight"] != frame.flight:
            raise ValueError(
                f"{photo_id}: the key says flight {record['flight']}, the pack {frame.flight}"
            )
        if frame.flight in TUNING_FLIGHTS:
            raise ValueError(
                f"{photo_id} is on flight {frame.flight}, a tuning flight: the matcher was"
                " tuned on its ground, so it cannot test it"
            )
        position = (float(record["true_position"]["x"]), float(record["true_position"]["y"]))
        if any(
            math.dist(position, seen.centre) < frame.reach_m + seen.reach_m + ONBOARD_DRIFT_M
            for seen in tuning
        ):
            overlapping.append(photo_id)
            continue
        kept.append(
            KeyedFrame(
                photo_id=photo_id,
                flight=frame.flight,
                sclk=frame.sclk,
                true_position=position,
                true_heading_deg=float(record["true_heading_deg"]),
                terrain_type=TerrainType(record["terrain_type"]),
                hard_mode=bool(record["hard_mode"]),
            )
        )
    flights = sorted({k.flight for k in kept})
    runs = [sorted((k for k in kept if k.flight == f), key=lambda k: k.sclk) for f in flights]
    return Plan(runs=runs, overlapping=overlapping)


def run_test(
    plan: Plan,
    load: Callable[[KeyedFrame], FrameInputs],
    matcher: Matcher,
    *,
    matcher_name: str,
    provenance: Provenance,
    results_dir: Path = REPO_ROOT / "results",
    script: Path = Path(__file__),
    inputs: Sequence[Path] = (),
) -> Path:
    """Fix and score every planned frame, write each fix and overlay, and the
    test summary through the shared scorer; returns the summary's path.
    `provenance` is the fixes'; the scorer records the summary's from
    `script` and `inputs`."""
    drone = results_dir / "drone"
    scored = []
    for run in plan.runs:
        previous = None
        for key in run:
            started = time.perf_counter()
            frame = load(key)
            centre = search_centre(frame.onboard, previous)
            ground = straighten(frame.raw, frame.camera, RESOLUTION)
            window = read_map_window(frame.crop, centre, SEARCH_RADIUS_M + HALF_SIZE_M)
            try:
                estimate = locate_on_map(ground, window, matcher)
                counts = (estimate.matches, estimate.inliers)
                position, heading = estimate.position, estimate.heading_deg
            except NoFix as no_lock:
                # No lock: the crew would still have the search centre, so that is the fix.
                estimate = None
                counts = (no_lock.matches, no_lock.inliers)
                position, heading = centre, ground.heading_deg
            seconds = time.perf_counter() - started

            overlay = drone / "overlays" / f"{key.photo_id}-{matcher_name}-{uuid4().hex}.png"
            fix = score_fix(
                jezero_fix_result(
                    photo_id=key.photo_id,
                    position=position,
                    heading_deg=heading,
                    time_per_fix_s=round(seconds, 2),
                    terrain_type=key.terrain_type,
                    overlay=recorded(overlay),
                    provenance=provenance,
                ),
                Point(x=key.true_position[0], y=key.true_position[1]),
                key.true_heading_deg,
            )
            searched = "the previous fix" if previous else "the onboard position"
            title = _title(key, fix, counts, matcher_name, searched, locked=estimate is not None)
            draw_overlay(window, ground, estimate, frame.onboard, title, overlay, fix, counts)
            path = drone / "fixes" / f"{key.photo_id}.json"
            with written_atomically(path) as partial:
                partial.write_text(fix.model_dump_json(indent=2) + "\n", encoding="utf-8")
            scored.append(fix)
            if estimate is not None:
                previous = PreviousPhoto(fix=position, onboard=frame.onboard)

    hard_mode = [key.photo_id for run in plan.runs for key in run if key.hard_mode]
    return write_test_summary(
        scored,
        test=TEST,
        script=script,
        inputs=list(inputs),
        extra_groups={"hard_mode": hard_mode} if hard_mode else None,
        results_dir=results_dir,
    )


def _title(
    key: KeyedFrame,
    fix: FixResult,
    counts: tuple[int, int],
    matcher_name: str,
    searched: str,
    locked: bool,
) -> str:
    matches, inliers = counts
    terrain = key.terrain_type.value + (", hard mode (sand ripples)" if key.hard_mode else "")
    found = (
        f"{inliers} of {matches} matches agree (cyan); the frame laid on the map by the fit"
        f" in 4 m squares, its outline (red)"
        if locked
        else f"NO LOCK: {inliers} of {matches} matches agree ({MIN_INLIERS} needed), so the fix"
        " is the search centre"
    )
    return "\n".join(
        [
            f"Drone test at Jezero, flight {key.flight}, {key.photo_id} ({terrain})",
            f"{matcher_name}, {fix.time_per_fix_s:.1f} s, searched around {searched}."
            " Left: the frame straightened to the HiRISE 25 cm map, north up.",
            f"Right: {found}; onboard position (yellow x).",
            f"Fix (green) is {fix.truth.position_error_m:.2f} m and"
            f" {fix.truth.heading_error_deg:.1f}° from Person 4's answer key (magenta cross).",
        ]
    )


def footprint_reach_m(raw: np.ndarray, camera: DroneFrame) -> float:
    """How far from the nadir the frame's straightened view sees ground, metres."""
    ground = straighten(raw, camera, RESOLUTION)
    rows, cols = np.nonzero(ground.valid)
    return float(np.hypot(cols - ground.nadir_px[0], rows - ground.nadir_px[1]).max()) * RESOLUTION


def main(matcher_name: str) -> None:
    from route.answer_key import read_answer_key

    root = data_root()
    jezero = root / "jezero"
    frames_csv = jezero / "pack" / "frames.csv"
    waypoints = jezero / "source" / "nasa" / "m20_heli_waypoints.json"
    answer_key = jezero / "answer-key"
    keys = read_answer_key(root)
    if not keys:
        raise SystemExit(f"no answer-key frames in {answer_key}; Person 4 keys them (P4-01)")
    exclusions = json.loads((answer_key / "flights.json").read_text())
    if not {k["flight"] for k in keys} <= set(exclusions["excluded_flights"]):
        raise SystemExit(f"{answer_key / 'flights.json'} does not list every keyed flight")

    with frames_csv.open() as f:
        rows = {row["product"].removesuffix(".IMG"): row for row in csv.DictReader(f)}
    keyed = {k["photo_id"] for k in keys}
    pack, tuning, inputs = {}, [], [frames_csv, waypoints, answer_key / "flights.json"]
    inputs += [answer_key / "keys" / f"{photo_id}.json" for photo_id in sorted(keyed)]
    for photo_id, row in rows.items():
        flight = int(row["flight"])
        if photo_id not in keyed and flight not in TUNING_FLIGHTS:
            continue
        label = label_path(jezero, row)
        camera = read_drone_frame(label.read_text())
        if camera.file_stem != photo_id or camera.flight != flight:
            raise SystemExit(f"{label} does not belong to {photo_id} on flight {flight}")
        with rasterio.open(label) as src:
            reach = footprint_reach_m(src.read(1), camera)
        pack[photo_id] = PackFrame(flight=flight, sclk=camera.sclk, reach_m=reach)
        if flight in TUNING_FLIGHTS:
            tuning.append(Footprint(centre=frame_onboard(camera, waypoints), reach_m=reach))
        inputs += [label, label.with_suffix(".IMG"), jezero / "pack" / "crops" / row["crop"]]
    plan = plan_runs(keys, pack, tuning)

    def load(key: KeyedFrame) -> FrameInputs:
        row = rows[key.photo_id]
        label = label_path(jezero, row)
        camera = read_drone_frame(label.read_text())
        with rasterio.open(label) as src:
            raw = src.read(1)
        crop = jezero / "pack" / "crops" / row["crop"]
        return FrameInputs(
            raw=raw, camera=camera, crop=crop, onboard=frame_onboard(camera, waypoints)
        )

    matcher, device, weights = load_matcher(matcher_name, root)
    inputs = sorted(set(inputs)) + weights
    # Before anything is written: refuse uncommitted fix code, checksum the inputs.
    made_by = provenance(Path(__file__), FIX_CODE + ["route/answer_key.py"], inputs)
    summary_path = run_test(
        plan, load, matcher, matcher_name=matcher_name, provenance=made_by, inputs=inputs
    )

    summary = json.loads(summary_path.read_text())
    run = sum(len(r) for r in plan.runs)
    print(f"wrote {recorded(summary_path)}: {run} frames, {matcher_name} on {device.type}")
    if plan.overlapping:
        print(
            f"left out {len(plan.overlapping)} keys whose ground a flight"
            f" {sorted(TUNING_FLIGHTS)} frame may have seen: {', '.join(plan.overlapping)}"
        )
    if run < KEY_FRAMES_WANTED:
        print(f"only {run} frames scored; the ticket wants at least {KEY_FRAMES_WANTED}")
    for name, group in [("overall", summary["overall"]), *summary["groups"].items()]:
        print(
            f"  {name:9} n {group['n']:3}  median {group['median_error_m']:.2f} m"
            f"  within 1/5/10 m {group['within_1m_pct']:.1f}/{group['within_5m_pct']:.1f}/"
            f"{group['within_10m_pct']:.1f}%"
        )
    print(f"  JPL's benchmark: {JPL_WITHIN_5M_PCT}% within 5 m, {JPL_WITHIN_10M_PCT}% within 10 m")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--matcher", choices=["loftr", "lightglue"], default="loftr")
    args = parser.parse_args()
    if not os.environ.get("REDMARK_DATA"):
        sys.exit("set REDMARK_DATA to the shared data folder with the pack, key and weights")
    main(args.matcher)
