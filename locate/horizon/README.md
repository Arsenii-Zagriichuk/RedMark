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

## First horizon fix (P3-02)

`uv run python -m locate.horizon.fix` turns Navcam frames into fix results in `results/horizon/fixes/`, each with its overlay in `results/horizon/overlays/p3-02-<photo id>.png` (the photo skyline on the matched calculated skyline, the match cost over the grid with the fix, its circle and the true position, and the frames with the skyline found in each).

- **Skyline in the photo** (`sky.py`): in each column, the first strong downward step in brightness below the smooth sky, found with a short, wide box (so the hazy crater rim survives) and placed with a narrow one; a running median removes single-column misreads, and columns where the skyline leaves the top of the frame give none.
- **Heading and elevation of each skyline pixel** (`navcam.py`): the frame's CAHVOR camera model (the R distortion, under 0.01° for Navcam, is left out) and the rover attitude from the label. The label's site-frame pointing is the look of the detector's centre pixel, and the code reproduces it to 0.001°.
- **Match** (`match.py`): the matcher gets the skyline's azimuths relative to the photo's own pointing, not its heading, and its elevations (a level sensor, no compass). Every grid spot and every 0.25° heading is scored by the clipped mean difference (at most 1° a sample), so misread haze can't drag the match away.
- **Fix result:** the best grid spot and heading; uncertainty circle out to the farthest spot whose cost is within 1.5× the best (never under the grid's 71 m half-diagonal); confidence 0 until the hidden-pile test (P3-03) measures it; truth from PLACES (rover position plus the camera's offset) and the label's pointing, scored through the shared scorer. Time per fix excludes loading the grid once.

Frames: the 12-frame Navcam horizon ring at sol 3655, site 98, drive 1520 (sequence NCAM00266), the P3-01 check stop and so tuning pile. Two fixes come out: one frame alone (`NRB_721967057…`, facing the slopes of Mount Sharp, picked before any run) and the whole ring combined (`sol3655-site98-drive1520-NCAM00266`), placed relative to its first frame by their labels. The results files hold the numbers; the ring lands on the grid spot next to the truth with a sub-degree heading error, while one 45° frame alone, here a nearly level stretch of skyline, matches a wrong spot and heading.
