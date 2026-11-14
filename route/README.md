# route/

Owner: Person 4 (route and simulation).

The route engine behind `POST /route`: cost map, fastest safe, science and cart routes, limit checks.

- `engine.py`: `plan(request: dict) -> dict`, the function the service calls for `POST /route` (RouteRequest in, RouteResponse out). When every path breaks a hard limit it raises `NoSafeRoute`, which the service returns to the app as a 422 with the reason, so no returned route ever breaks a hard limit. Start and goal in the same planning cell, or a site with no habitat, are also a 422; the science and cart modes are a 501 until P4-04.
- `planner.py`: the cost map (seconds to walk each cell: Tobler's hiking function on slope, loose sand x1.6, ridges x3) and the minimum-cost path (scipy Dijkstra over 8-neighbour steps). `blocked_cells` gives the cells no route may enter: steeper than the slope limit, without slope data, or beyond the distance from the habitat. A diagonal step between two blocked cells that touch at a corner is not allowed, so no path slips through a diagonal wall; the open cells beside it stay walkable.
- `layers.py`: reads the layers onto a 4 m planning grid over the walk area, keeping the worst pixel in each cell; a cell with any pixel of no data has no data.
- `plot_route.py`: the overlay image, `route/overlays/p4-03-fastest.png`, shading `blocked_cells`.

**Exact endpoints.** The search runs between planning-cell centres, but the route runs from the exact start to the exact goal: the stretch from each exact point (and the habitat) to its cell's centre is walked at that cell's pace and counted in the time, the walk-back margin and the distance from the habitat.

**Walk-back margin.** The least spare time at any point of the route: the walk-time limit minus the time walked so far and the fastest safe walk from that point back to the habitat. Within the habitat's cell, the return leg goes directly to the habitat at that cell's pace, so no return travel is charged after arrival. A route whose margin would go negative is refused with `NoSafeRoute`; the `walk_back` limit check itself comes with P4-04.

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
