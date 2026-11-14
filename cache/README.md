# cache/

Owner: shared.

The demo cache: `demo/<producer>/<step>.json`, one saved response per step of the 3-minute demo, due H16. Each producer writes only its own subfolder; the service's recorder (P1-02) writes them too. Every JSON file here must match a contract.

Images the cached responses name, for the offline demo to bundle: the horizon demo fixes' overlays are in `demo/horizon/overlays/`, under the file name of each fix result's `overlay` (written by `locate/horizon/demo_fixes.py`).

The simulated Gale drone fix (`locate/drone/gale_fix.py`, P2-07) is saved as `demo/fixes/drone-fix-gale.json` (step `drone.fix.gale`, `GET /fixes/drone/gale-sim-drone-0001`); its overlay and its drone photo are copied to `demo/drone/overlays/` under their file names in `results/drone/overlays/`. It sits on the walk planned from `sites/gale.yaml` (base camp to the first science target, fastest, 20°), so the Plan screen's steps must come from the same site config. `prep/gale/demo_cache.py` re-records them through the service: `demo/sites/plan-site.json`, `demo/layers/plan-layers.json`, and in `demo/route/` the fastest and science walks to every science target and the cart route, at 20° and 15°. A route the engine refuses is saved with its 422 status and reason, so demo mode shows the refusal instead of a cache miss. Rerun it, then `gale_fix.py`, whenever `sites/gale.yaml`, the layers or the route engine change.
