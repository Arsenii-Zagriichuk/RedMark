# route/

Owner: Person 4 (route and simulation).

The route engine behind `POST /route`: cost map, fastest safe, science and cart routes, limit checks.

- `engine.py`: `plan(request: dict) -> dict`, the function the service calls for `POST /route` (RouteRequest in, RouteResponse out), for all three modes:
  - **fastest**: the quickest walk that keeps every hard limit.
  - **science**: the science alternative. It visits every science target in `sites/<site>.yaml` it can reach, in the quickest order (every order is tried, fine for the handful of targets a walk has: 8 take under 2 s); while that breaks a hard limit it drops the target whose visit costs the most time. Targets outside the planning grid are skipped before the search; the start, goal and habitat must still be mapped. `extra_time_vs_fastest_s` is its extra time over the fastest route.
  - **cart**: the cart's own cost map, which cannot cross a ridge on the ridge map. It goes from the request's start to its goal (the app sends the habitat to the base camp). The walk-back rule and daylight are crew rules, so the cart's checks are slope, distance from the habitat, speed, time and hazard margin. An unreachable habitat does not refuse a cart route; its required `walk_back_margin_s` field is then 0 (not applicable).

  Daylight runs from first light (the first step of the replayed sol's conditions file with the sun above the horizon) to its sunset, in Mars hours of 88775.244 s / 24; a sol whose sun never rises has no daylight, so every crew route is refused. When every path breaks a hard limit, `plan` raises `NoSafeRoute`, which the service returns to the app as a 422 with the reason, so no returned route ever breaks a hard limit. Start and goal in the same planning cell, or a site with no habitat, are also a 422.
- `planner.py`: the cost map (seconds to walk each cell: Tobler's hiking function on slope, loose sand x1.6, ridges x3) and the minimum-cost path (scipy Dijkstra over 8-neighbour steps, from the habitat, the start and every science target at once). `blocked_cells` gives the cells no route may enter: steeper than the slope limit, without slope data, or beyond the distance from the habitat; for the cart, ridges too. A diagonal step between two blocked cells that touch at a corner is not allowed, so no path slips through a diagonal wall; the open cells beside it stay walkable. Limit checks: slope, distance from the habitat, planning speed, walk time, and for the crew walk-back and daylight (spare seconds, at least 0).
- `layers.py`: reads the layers onto a 4 m planning grid over the walk area, keeping the worst pixel in each cell; a cell with any pixel of no data has no data.
- **Hazard margin**: a hazard is a cell steeper than the slope limit or with no slope data. No route enters a cell closer to a hazard than the request's `uncertainty_m`, so the whole uncertainty circle stays off the hazard and the route moves away from hazards as the circle grows. Each hazard sits at its cell's centre; the route is measured along every stretch, not just at its points, and a diagonal step across a corner inside the circle is never taken. A start or goal already inside the circle is refused with "stop and take a fix". The `hazard_margin` check is the nearest hazard to the route against the circle, for every mode (with no hazard on the map, the walk area's diagonal).
- `plot_hazard_margin.py`: `route/overlays/p4-06-hazard-margin.png`, the route past a made-up steep drop with a 5 m and a 25 m circle (the stub map has no hazards).
- **Location-aware routing** (P4-07): the search prefers ground where position finding works, from layer 5's location quality (0 to 1, landmark view and the error map together). Each cell's search cost is its walking time x (1 + `LOCATION_WEIGHT` x (1 - quality)), with `LOCATION_WEIGHT` 1 (a RedMark choice; 0 turns it off, and `plan_on_grid` takes `location_weight`). Every reported time is still walking time, and the walk home used for walk-back and daylight is the fastest one. Location quality is a preference, never a hard limit: when the preferred route breaks a hard limit, the route is planned again on walking time alone before it is refused. The raster is read from the site config's `location_quality` key, each 4 m cell keeping its lowest pixel (an unknown one counts as 0); with no key, quality is 1 everywhere and routing is unchanged.
- **Checkpoints**: the crew's routes visit the best-scoring of Person 3's checkpoint candidates (`layers/location_quality/layer5-<site>.json`) near each 500 m stretch of the route, within 250 m of it, and list them in walking order. A candidate off the map, on ground no route may enter, inside a hazard's circle or cut off from the habitat is never chosen. While a route through the chosen ones breaks a hard limit, the checkpoint costing the most to visit (in search cost) is dropped. Science targets keep their order, each checkpoint going between the waypoints it falls between. The cart's route has none.
- **Visit fallback**: before excluding a science target or dropping a checkpoint, retry the same ordered visits on walking time alone. A preferred path that already keeps every hard limit is retained; if neither search keeps them, pruning continues without disabling the preference for the remaining route. Walking-time searches are reused across subsets of the same visits. `extra_time_vs_fastest_s` remains the difference in actual walking time from the preferred fastest route, so it can be negative when the science alternative takes a quicker, poorer-quality path.
- `plot_location_aware.py`: `route/overlays/p4-07-location-aware.png`, a route past poor ground on a made-up grid with and without location-aware routing (the stub map has no location-quality raster).
- `plot_route.py`: the overlay image, `route/overlays/p4-04-routes.png`: the three routes, the science targets, the base camp and `blocked_cells`.

**Exact endpoints.** The search runs between planning-cell centres, but the route runs from the exact start to the exact goal: the stretch from each exact point (and the habitat) to its cell's centre is walked at that cell's pace and counted in the time, the walk-back margin and the distance from the habitat.

A direct walk within one cell is used only when it keeps the hazard margin; otherwise it goes via the cell centre. Every point-to-centre connection is also checked, including the habitat's. These same safe travel times feed the walk-back and daylight checks.

**Walk-back margin.** The least spare time at any point of the route: the walk-time limit minus the time walked so far and the fastest safe walk from that point back to the habitat. Within the habitat's cell, the return leg goes directly to the habitat at that cell's pace when that stretch keeps the hazard margin, or via the cell centre otherwise. No return travel is charged after arrival. A route whose margin would go negative is refused with `NoSafeRoute`; the same goes for daylight, counted up to being back at the habitat.

Run `uv run python -m route.plot_route` to redraw the overlay.

## Layer files the route needs

The engine reads three rasters. Each is a single-band GeoTIFF in the site's projection (`projection` in `sites/<site>.yaml`), anywhere inside `REDMARK_DATA`, and named under `files` in the site config by its key:

| Key | Band values | Comes from |
| --- | --- | --- |
| `slope` | slope in degrees; nodata where unknown | layer 1, slope from the 1 m terrain (P2-02) |
| `sand` | non-zero on loose sand, 0 on firm ground | layer 2, THEMIS sand vs rock (P2-03) |
| `ridges` | non-zero on a boxwork ridge, 0 elsewhere | layer 2, ridge map from the 25 cm photos (P2-03) |

```yaml
# sites/gale.yaml
files:
  base_map: gale/layers/base
  slope: gale/rasters/slope.tif
  sand: gale/rasters/sand.tif
  ridges: gale/rasters/ridges.tif
```

- Any resolution works: each 4 m planning cell takes the highest pixel value inside it, so one steep metre or one ridge pixel is never averaged away.
- The rasters should cover the walk area (`bounds`). Cells with no slope data are never walked; cells with no sand or ridge data count as firm, ridge-free ground.
- No `slope` key: the engine plans on flat stub ground. A key whose file is missing is an error, so a typo can't quietly plan on flat ground.
- Adding the keys needs no code change here.
