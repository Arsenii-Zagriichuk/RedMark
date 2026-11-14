# route/

Owner: Person 4 (route and simulation).

The route engine behind `POST /route`: cost map, fastest safe, science and cart routes, limit checks.

- `api.py`: `plan(RouteRequest) -> RouteResponse`, the one call the service makes. Raises `NoSafeRoute` when every path breaks a hard limit, so no returned route ever breaks one.
- `engine.py`: the cost map (seconds to walk each cell: Tobler's hiking function on slope, loose sand x1.6, ridges x3) and the minimum-cost path (scikit-image `MCP_Geometric`). Cells steeper than the slope limit, without slope data, or beyond the distance from the habitat cannot be entered, and blocked cells touching only at a corner are sealed so a diagonal step can't slip through a wall.
- `layers.py`: reads the layers onto a 4 m planning grid over the walk area, keeping the worst pixel in each cell.
- `plot_route.py`: the overlay image, `results/route/overlays/p4-03-fastest.png`.

**Layer files the engine reads.** GeoTIFFs in the site projection, named in `sites/<site>.yaml` under `files`, relative to `REDMARK_DATA`:

| Key | Values | Producer |
| --- | --- | --- |
| `slope` | slope in degrees; nodata where unknown | Person 2, P2-02 |
| `sand` | non-zero on loose sand, 0 on firm ground | Person 2, P2-03 |
| `ridges` | non-zero on a boxwork ridge, 0 elsewhere | Person 2, P2-03 |

With no `slope` key the engine plans on flat stub ground; a key whose file is missing is an error.

**Walk-back margin.** The least spare time at any point of the route: the walk-time limit minus the time walked so far and the fastest safe walk from that point back to the habitat. A route whose margin would go negative is refused with `NoSafeRoute`; the `walk_back` limit check itself comes with P4-04.

Run `uv run python -m route.plot_route` to redraw the overlay.
