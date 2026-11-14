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

`uv run python -m locate.horizon.fix` turns Navcam frames into fix results in `results/horizon/fixes/`, each with its overlay in `results/horizon/overlays/p3-02-<photo id>.png` (the photo skyline on the matched calculated skyline; the fix, its circle and the true position on the base map, over the match cost, and close up on the base map; and the frames with the skyline found in each). The base map is read through the layer contract from `sites/gale.yaml`'s `base_map` (`base_map.py`), with its title on the panel: it is the stub tile until P2-02 delivers the real one, and a rerun then draws on that with no code change.

- **Skyline in the photo** (`sky.py`): in each column, the first strong downward step in brightness below the smooth sky, found with a short, wide box (so the hazy crater rim survives) and placed with a narrow one; a running median removes single-column misreads, and columns where the skyline leaves the top of the frame give none.
- **Heading and elevation of each skyline pixel** (`navcam.py`): the frame's CAHVOR camera model (the R distortion, small beside the grid's 0.25° step, is left out) and the rover attitude from the label. The label's site-frame pointing is the look of the detector's centre pixel; a test checks the code gives JPL's number for a real frame.
- **Match** (`match.py`): the matcher gets the skyline's azimuths relative to the photo's own pointing, not its heading, and its elevations (a level sensor, no compass). Every grid spot and every 0.25° heading is scored by the clipped mean difference (at most 1° a sample), so misread haze can't drag the match away.
- **Fix result:** the best grid spot and heading; uncertainty circle out to the farthest spot whose cost is within 1.5× the best (never under half a grid cell's diagonal); confidence 0 until the hidden-pile test (P3-03) measures it; truth from PLACES (rover position plus the camera's offset) and the label's pointing, scored through the shared scorer. Time per fix excludes loading the grid once.

Frames: the 12-frame Navcam horizon ring at sol 3655, site 98, drive 1520 (sequence NCAM00266), the P3-01 check stop and so tuning pile. Two fixes come out: one frame alone (`NRB_721967057…`, facing the slopes of Mount Sharp, picked before any run) and the whole ring combined, placed relative to its first frame by their labels. A fix's photo id and heading belong to its reference photo, the first frame: the ring fix is `NRB_721967002…`, and its heading is that frame's pointing. The results files hold the numbers; the ring lands on the grid spot next to the truth with a sub-degree heading error, while one 45° frame alone, here a nearly level stretch of skyline, matches a wrong spot and heading.

## Horizon test on the hidden pile (P3-03)

`uv run python -m locate.horizon.hidden_pile` fetches the hidden pile from the PDS Imaging Node into `$REDMARK_DATA/navcam/hidden/` (`hidden_pile.py`); `uv run python -m locate.horizon.hidden_test` then makes one fix per hidden stop and writes the test summary `results/horizon/horizon-gale.json` through the shared scorer, with a fix result in `results/horizon/fixes/` and an overlay `results/horizon/overlays/p3-03-<photo id>.png` for every stop, ready for the Test lab.

- **The split, by stretch of the traverse:** every stop at sites 96 to 100 (round the sol 3655 ring at site 98, which the grid check and the first fix were tuned on) is tuning pile. The other Curiosity stops in the walk area are cut into 20 runs in traverse order, and from each run the first stop (by sol) with a horizon ring is taken, before any fix is run on it.
- **A horizon ring:** the stop's reduced right-Navcam frames (full, subframe or downsampled; no thumbnails) that point within 20° of level, from the one sequence that covers the most skyline, if it covers at least 300°. A sky movie (one direction many times) or a ground mosaic is not a ring.
- **The fix:** exactly as the first fix makes it (`fix.py`), with no setting changed after looking at hidden frames. Confidence stays 0: what it measures is still open in the contracts.
- **Splits:** by terrain type, and hollow against ridge top or open ground, both from the 1 m terrain round the rover's PLACES position (`terrain_labels.py`). A hollow sits more than 1 m below the mean ground within 50 m; textured ground departs from its best-fit plane within 10 m by more than 0.15 m (root mean square), and anything smoother is plain. A group with no stops is left out of the summary, and the run says so.
- **Isolation:** `tests/test_hidden_pile_isolation.py` fails if any Python file other than those two scripts names the hidden-pile folder.
