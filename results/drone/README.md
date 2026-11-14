# results/drone/

Owner: Person 2 (data and drone matcher). Written by `locate/drone/first_fix.py` (P2-05); see `locate/drone/README.md` for how the fix is made.

If you use these files (the app's Test lab and Drone fix screen, Person 1; the walk simulation, Person 4), read this first. `GET /fixes/drone` lists both sites' fixes; filter by `site`.

## Files

- `fixes/<frame>.json`: the most recently written drone fix per Ingenuity frame, in the fix result contract (`contracts/schemas/fix_result.json`). Positions are map metres in the Jezero site frame (`sites/jezero.yaml`), where map metres are ground metres. Fixes written by the drone test (P2-06, `locate/drone/score_jezero.py`) are scored: `truth` holds Person 4's answer key and the error.
- `drone-jezero.json`: the drone test's summary (P2-06), written through the shared scorer. Until the test has run on the answer key it is a stub (`provenance.script: "stub"`); never show its numbers as real.
- `overlays/<frame>-<matcher>-<run-id>.png`: each new run writes its own overlay. The PNG's `fix_result` text field holds the complete fix result, with correspondence counts in `matches` and `inliers`. The current fix in `fixes/` links to its overlay. Earlier overlays use `<frame>-<matcher>.png`.
- `fixes/gale-sim-drone-0001.json`: the simulated Gale drone fix for the demo (P2-07, `locate/drone/gale_fix.py`), in the Gale site frame (`sites/gale.yaml`). Its position is the crew: the midpoint of the two detected astronauts. `simulated` is true and `truth` null. Its `overlay` shows the drone photo with the detected astronauts next to the map with the photo's matched outline, the astronauts, the crew's fix and the demo route. `overlays/gale-sim-drone-0001-photo-<run-id>.png`, from the same run, is the drone photo alone with the detected astronauts, for the Drone fix screen. Both images embed the fix result (`fix_result`) and each detected astronaut's map position and heading (`astronauts`, JSON) as PNG text.
- `fixes/stub-ingenuity-0001.json` is a stub (`provenance.script: "stub"`); never show its numbers as real.

## What the numbers mean, and don't yet

- `uncertainty_m: 10` and `confidence_pct: 0` are placeholders, not measurements: the project's 5–10 m drone target and no claimed confidence. They are named constants in `locate/drone/fix.py`, and the fix result has no field that says so. They are not fitted to the answer key (it is the test); the drone test's `within_10m_pct` is how often the 10 m circle holds the truth. Do not present them as measured.
- `truth` is null on the P2-05 fixes (flight 10, the tuning flight, which is never scored). Fixes from the drone test carry `truth`. A frame the matcher could not lock on still has a fix, at its search centre, and it counts in the summary.
- `simulated` is false for the Jezero fixes: real Navcam frames matched to the real HiRISE map. The Gale drone fix (P2-07) is simulated: its photo is cut from the same Gale map it is matched to, so it shows the pipeline, not accuracy. Never report an error or accuracy number from it; it has none.
- `terrain_type` on the P2-05 fixes comes from the Jezero pack's hard-mode flag (plain for the sand-ripple flight, textured otherwise). The drone test uses Person 4's by-eye tags from the answer key.
- `time_per_fix_s` covers reading the frame through fitting the fix, on Person 2's GPU. It leaves out loading the matcher's weights and drawing the overlay.

## For Person 1: a dependency in your files

P2-05 adds `kornia` (LoFTR, DISK and LightGlue) to the existing `gpu` dependency group in `pyproject.toml` and `uv.lock`. CI and the app do not install that group, so nothing changes for them. Only Person 2's machine runs `uv sync --group gpu`.
