# results/drone/

Owner: Person 2 (data and drone matcher). Written by `locate/drone/first_fix.py` (P2-05); see `locate/drone/README.md` for how the fix is made.

If you use these files (the app's Test lab and Drone fix screen, Person 1; the walk simulation, Person 4), read this first.

## Files

- `fixes/<frame>.json`: one drone fix per Ingenuity frame, in the fix result contract (`contracts/schemas/fix_result.json`). Positions are map metres in the Jezero site frame (`sites/jezero.yaml`), where map metres are ground metres.
- `overlays/<frame>-loftr.png`: the fix's overlay, which `overlay` in the fix result names. `overlays/<frame>-lightglue.png` is the LightGlue fallback on the same frame, kept as evidence; it has no fix result of its own.
- `fixes/stub-ingenuity-0001.json` is a stub (`provenance.script: "stub"`); never show its numbers as real.

## What the numbers mean, and don't yet

- `uncertainty_m: 10` and `confidence_pct: 0` are placeholders, not measurements: the project's 5–10 m drone target and no claimed confidence. They are named constants in `locate/drone/fix.py`, and the fix result has no field that says so. P2-06 replaces them with values measured on Person 4's answer key (P4-01). Until then, do not present them as measured.
- `truth` is null and there is no error yet: the frames are not scored until the answer key exists. P2-06 adds scored fixes and the test summary `drone-jezero.json`.
- `simulated` is false: these are real Navcam frames matched to the real HiRISE map. The Gale drone fixes (P2-07) will be simulated and labelled so.
- `terrain_type` comes from the Jezero pack's hard-mode flag for now (plain for the sand-ripple flight, textured otherwise). P2-06 switches to P4-01's by-eye tags.
- `time_per_fix_s` covers reading the frame through fitting the fix, on Person 2's GPU. It leaves out loading the matcher's weights and drawing the overlay.

## For Person 1: a dependency in your files

P2-05 adds `kornia` (LoFTR, DISK and LightGlue) to the existing `gpu` dependency group in `pyproject.toml` and `uv.lock`. CI and the app do not install that group, so nothing changes for them. Only Person 2's machine runs `uv sync --group gpu`.
