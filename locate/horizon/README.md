# locate/horizon/

Owner: Person 3 (horizon matcher and location quality).

The horizon grid and skyline matcher at Gale. Writes to `results/horizon/`.

## Horizon grid (P3-01)

`uv run python -m locate.horizon.grid` calculates the 360° skyline (horizon elevation in every direction from map north) for a square grid of spots across the walk area in `sites/gale.yaml`, and caches it in `$REDMARK_DATA/gale/horizon/grid.npz` with `grid-meta.json` (settings, timings, MOLA offset, provenance). `uv run python -m locate.horizon.plot_grid` then draws the overlays in `results/horizon/overlays/`.

- **Terrain, finest first:** the 1 m Gale terrain within 1 km of the spot; a 10 m averaged copy of the whole Gale file; MOLA 463 m beyond it (the top of Mount Sharp and most of the crater rim), shifted by the median Gale-minus-MOLA height where they overlap. Rays reach 120 km.
- **Curvature:** every sample sits on the 3,396,190 m sphere, so ground 60 km away is about 0.5° lower than on a flat map.
- **Eye height:** 1.9 m, Curiosity's Navcam.

Last run (stub walk area, 4 × 4 km; a new walk area is a rerun, not a code change):

| Setting | Value |
| --- | --- |
| Grid spacing | 100 m, 41 × 41 = 1,681 spots |
| Directions | every 0.25° (1,440 per spot), 1,664 samples per ray from 5 m to 120 km |
| MOLA offset | −11.15 m |
| Computing time | 205 s on one laptop core, plus 2 s to load cached terrain (about 30 s the first time) |
