# sim/

Owner: Person 4 (route and simulation).

The walk simulation behind `POST /simulate`: Kalman filter, fix schedule, break-it scenarios, lost mode.

- `engine.py`: `simulate(request: dict) -> dict`, the function the service calls. It walks the path at the 2 km/h planning speed in 10 s ticks (plus a tick at each scheduled fix) and tracks the true and estimated position with a simple Kalman filter:
  - Between fixes, visual odometry, the motion sensor, step counting and the sun carry the position. Each step models per-axis drift sigma as 2.5% of the distance walked (based on MER visual odometry, Maimone, Cheng & Matthies 2007), so the circle grows. Drift uses distance along the path, not the straight-line displacement between ticks, so turns and backtracking still accumulate uncertainty.
  - A fix in `fix_schedule` shrinks the circle. Its error size comes from that method's test summary: `results/horizon/horizon-gale.json`, `results/ground/ground-gale.json`, `results/drone/drone-jezero.json`. The median error is read as a 2D normal error (median radius = sigma x sqrt(2 ln 2)). Swapping a stub summary for the real one needs no code change. No fix is taken as better than 1 cm, so a summary reporting no error still leaves a circle.
  - Each fix timestamp has two ordered samples: the predicted state, then the corrected state with the `fix` event. They share `t_s`; play samples in array order to show the actual uncertainty reduction. Simultaneous fixes are applied together between those samples. A noisy fix can leave the corrected circle wider than the preceding 10 s tick, but smaller than its prediction; no covariance is artificially clamped.
  - The uncertainty circle is the 95% radius, so `confidence_pct` is 95 at every step.
  - **Radio ranging (SIMULATED)**: while the radio is up, signal timing to the habitat and to the buddy is one position update every 60 s with an assumed 5 m error per axis, so the circle stays small. Its first update carries a `radio_ranging_simulated` event, for the app's label.
  - A `fix_requested` event fires when the circle passes 3 m near hazards, 5 m in boxwork, or 10 m on open ground. Entering more restrictive terrain can request a fix or escalate an outstanding request. Requests do not repeat at every tick; shrinking below the limit rearms them. Only scheduled fixes are taken. Near a hazard, the existing `stop_for_fix` event still tells the crew to stop once the circle passes 3 m.
  - Runs are seeded: the same request and input files replay the same walk, including fixes. Positive and negative integer seeds are supported.
- `terrain.py`: reads the `slope` and `ridges` GeoTIFF paths in `sites/<site>.yaml`, relative to `REDMARK_DATA`. It samples cells touched by the estimated position's uncertainty circle, not the true position. Slopes above 20 degrees are hazards; positive ridge cells identify boxwork. Hazards take priority over boxwork. Rasters are opened once per run, sampled in the site's projection, and read in small windows. Unknown or off-map terrain uses the 3 m request limit. A missing configured file is an error, except when the caller explicitly supplies `hazard_distance_m`: that existing interface can run without map files, and unavailable layers still use the conservative 3 m limit. Sites with neither raster entry keep the stub's open-ground behavior.
- **Break-it scenarios** (`break_it` in the request); each lost source is an event at `t_s` 0:
  - `camera_off`: no visual odometry; the motion sensor, step counting and the sun drift at 5% of the distance walked (pedestrian dead reckoning, Jimenez et al. 2009). The buddy's camera takes the horizon and ground fixes, shared over the short-range radio: `fix` plus `buddy_camera`.
  - `radio_off`: offline mode (`mode: "offline"`), no radio ranging.
  - `drone_grounded`: drone fixes are greyed out: `fix_unavailable` with `method: "drone"`.
  - Camera and radio both off: no horizon or ground fix can reach the crew (`fix_unavailable`).
  - Everything at once: no fix can reach the crew, so when the circle passes 10 m the run switches to lost mode (`mode: "lost"`, one `lost_mode` event) for the rest of the walk.

  Event kinds: `fix`, `fix_requested`, `fix_unavailable`, `buddy_camera`, `stop_for_fix`, `lost_mode`, `camera_off`, `radio_off`, `drone_grounded`, `radio_ranging_simulated`.
- `cache_runs.py`: writes the demo cache's five break-it runs, `cache/demo/simulate/walk-simulate-<scenario>.json` (step ids `walk.simulate.normal`, `.camera-off`, `.radio-off`, `.drone-grounded`, `.everything`): the stub route, seed 1, with a horizon fix at 900 s, a drone fix at 1800 s and a ground fix at 2400 s. Each file holds the exact request body the app sends.
- `plot_walk.py`: the overlay image `sim/overlays/p4-05-walk.png` for the stub request: the tracks on the base map, the circle through the walk, and the terrain-dependent fix-request limits.
- `plot_break_it.py`: the overlay image `sim/overlays/p4-06-break-it.png`: the circle through each cached run.

Run `uv run python -m sim.cache_runs`, then `uv run python -m sim.plot_break_it` and `uv run python -m sim.plot_walk`, to redraw the cache and overlays.

Run `uv run pytest sim` for the simulation seams.
