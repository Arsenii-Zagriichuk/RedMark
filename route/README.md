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

## Drone answer-key tool (P4-01)

Set `REDMARK_DATA` to Person 2's shared data folder, then run:

```bash
uv run python -m route.key_frames
```

It reads `sites/jezero.yaml`, `jezero/pack/frames.csv`, the pack's frame PNGs and
reprojected flight crops, and each frame's PDS label at
`jezero/source/helicam/sol-<sol padded to 5 digits>/<photo_id>.xml`.
The labels must travel with the pack. No downloads or GPU are needed.
`--photo-id <id>` selects one frame; `--simulated` labels synthetic inputs.
Without `REDMARK_DATA`, the command refuses to write keys into stub data.

1. The left panel rectifies the Navcam's fisheye image using its calibration,
   height and attitude. The right panel is the crop in Jezero ground metres;
   crops in the published, equator-scale projection are refused.
2. Turn off the toolbar's zoom/pan mode, then alternate a photo feature and the
   same map feature. Select at least four pairs spread around the photo.
   **Undo** removes the pending point or last pair.
3. **Preview** draws the photo footprint and a translucent photo over the map.
   Check alignment, choose `textured` or `plain`, confirm the hard-mode tag,
   and tick **overlay checked** before **Save key**. A fit residual measures
   agreement between the clicked pairs, not position error against an answer key.
4. Saving advances to the next unkeyed frame. **Skip** advances without a key;
   closing the main window ends the session. Existing valid keys are never overwritten.

Saves stage and flush both complete payloads before publishing the overlay, then
the key JSON as the commit point. Restarting validates the JSON and PNG rather
than just checking whether the key filename exists. Incomplete keys, corrupt
overlays and orphan overlays are preserved under
`answer-key/incomplete/<photo_id>-<unique id>/`; the frame is then offered again.
Recovery does not delete those files. Read errors are reported, not treated as
corruption, and a frame being saved by another process is left alone.

Outputs stay separate from the pack and tuning inputs, under
`$REDMARK_DATA/jezero/answer-key/`:

- `keys/<photo_id>.json`: `true_position`, `true_heading_deg`, terrain type,
  hard-mode and simulated tags, the clicked pairs, transform and source
  checksums with the script's commit. Position is the camera's nadir; heading
  is the drone body's forward heading from map north, matching the drone fix.
  Clicks are in the rectified image, with pixel centres at integer coordinates,
  not the original PNG. No matcher predictions or onboard absolute positions
  become answer-key values.
- `overlays/<photo_id>.png`: the reviewed alignment on the map.
- `flights.json`: `excluded_flights` lists whole flights Person 2 must keep out
  of tuning, not just the keyed frames. It is updated before publishing a key.

Person 4 still keys and visually checks at least 20 real frames; the tool does
not invent their answer key. Pack sources are listed in `prep/data-manifest.yaml`.

```bash
uv run pytest route/tests/test_tie_points.py route/tests/test_answer_key.py
uv run python -m route.plot_tie_points
```

The latter redraws `overlays/p4-01-tie-points.png` from generated images,
explicitly labelled simulated; it is not a measured Jezero result.
