# sim/

Owner: Person 4 (route and simulation).

The walk simulation behind `POST /simulate`: Kalman filter, fix schedule, break-it scenarios, lost mode.

- `engine.py`: `simulate(request: dict) -> dict`, the function the service calls. It walks the path at the 2 km/h planning speed in 10 s ticks (plus a tick at each scheduled fix) and tracks the true and estimated position with a simple Kalman filter:
  - Between fixes, visual odometry, the motion sensor, step counting and the sun carry the position. Each step drifts by up to 2.5% of the distance walked (MER visual odometry, Maimone, Cheng & Matthies 2007), so the circle grows.
  - A fix in `fix_schedule` shrinks the circle. Its error size comes from that method's test summary: `results/horizon/horizon-gale.json`, `results/ground/ground-gale.json`, `results/drone/drone-jezero.json`. The median error is read as a 2D normal error (median radius = sigma x sqrt(2 ln 2)). Swapping a stub summary for the real one needs no code change.
  - The uncertainty circle is the 95% radius, so `confidence_pct` is 95 at every step.
  - A `fix_requested` event fires once each time the circle passes 10 m (open ground). The 5 m boxwork and 3 m near-hazard limits come once the sim reads the ridge and slope layers.
  - Runs are seeded: the same request replays the same walk.
  - Break-it flags are refused until P4-06.
- `plot_walk.py`: the overlay image `sim/overlays/p4-05-walk.png` for the stub request: the tracks on the base map and the circle through the walk.

Run `uv run python -m sim.plot_walk` to redraw the overlay.
