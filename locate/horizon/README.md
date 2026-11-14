# locate/horizon/

Owner: Person 3 (horizon matcher and location quality).

The horizon grid and skyline matcher at Gale. Writes to `results/horizon/`.

## Horizon grid (P3-01)

`uv run python -m locate.horizon.grid` calculates the 360° skyline (horizon elevation in every direction from map north) for a square grid of spots across the walk area in `sites/gale.yaml`, and caches it in `$REDMARK_DATA/gale/horizon/grid.npz` with `grid-meta.json` (settings, timings, far-terrain offset, provenance). `uv run python -m locate.horizon.plot_grid` then draws the grid overlays in `results/horizon/overlays/`.

- **Terrain, finest first:** the 1 m Gale terrain within 1 km of the spot; a 10 m averaged copy of the whole Gale file; the HRSC and MOLA blended terrain at 200 m beyond it (the top of Mount Sharp and most of the crater rim), shifted by the median Gale-minus-blend height where they overlap. The blend is a crop in degrees, read straight into map metres (59,274.7 m per degree on the same sphere). Rays reach 120 km.
- **Curvature:** every sample sits on the 3,396,190 m sphere, so ground 60 km away is about 0.5° lower than on a flat map.
- **Eye height:** 1.9 m, Curiosity's Navcam.

Last run (stub walk area, 4 × 4 km; a new walk area is a rerun, not a code change):

| Setting | Value |
| --- | --- |
| Grid spacing | 100 m, 41 × 41 = 1,681 spots |
| Directions | every 0.25° (1,440 per spot), 1,664 samples per ray from 5 m to 120 km |
| Far-terrain offset | −14.58 m |
| Computing time | 208 s on one laptop core, plus 2 s to load cached terrain (about 30 s the first time) |

### Check against a real Navcam panorama

`uv run python -m locate.horizon.plot_navcam_check` draws the skyline calculated at Curiosity's camera on sol 3655 (site 98, drive 1520, 331 m from the stub habitat; position from PLACES plus the mosaic label) on the 360° Navcam mosaic from that stop: `results/horizon/overlays/p3-01-navcam-sol3655.png`. From south-east to west it follows the near ridge line, and from 65° to 140° the upper slope of Mount Sharp behind the near mesas, which checks the far terrain and curvature. The crater rim to the north-west is too faint in the dust haze to confirm.
