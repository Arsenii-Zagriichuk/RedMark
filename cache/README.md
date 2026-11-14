# cache/

Owner: shared.

The demo cache: `demo/<producer>/<step>.json`, one saved response per step of the 3-minute demo, due H16. Each producer writes only its own subfolder; the service's recorder (P1-02) writes them too. Every JSON file here must match a contract.

Images the cached responses name, for the offline demo to bundle: the horizon demo fixes' overlays are in `demo/horizon/overlays/`, under the file name of each fix result's `overlay` (written by `locate/horizon/demo_fixes.py`).

The simulated Gale drone fix (`locate/drone/gale_fix.py`, P2-07) is saved as `demo/fixes/drone-fix-gale.json` (step `drone.fix.gale`, `GET /fixes/drone/gale-sim-drone-0001`); its overlay and its drone photo are copied to `demo/drone/overlays/` under their file names in `results/drone/overlays/`. It sits on the walk planned from `sites/gale.yaml` (base camp to the first science target, fastest, 20°), so `demo/sites/plan-site.json` (re-recorded through the service from that file) and the route and walk steps for that target must come from the same site config.
