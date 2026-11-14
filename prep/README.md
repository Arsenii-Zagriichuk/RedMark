# prep/

Owner: Person 2 (data and drone matcher).

Crops, reprojection, tiles and layer files for layers 1 to 3; the Jezero pack. Lists its data files in `data-manifest.yaml`.

## Jezero pack (P2-04)

`REDMARK_DATA=~/redmark-data uv run python -m prep.jezero.build_pack` builds the pack Person 4 keys the drone answer key on. Flights and margins are in `jezero/pack.yaml`. It writes `$REDMARK_DATA/jezero/pack/` (crops, frame images, overlays, `frames.csv`), `sites/jezero.yaml` and the Jezero entries in `data-manifest.yaml`.

Every Jezero position is in the site frame `+proj=eqc +lat_ts=18.4663 +lon_0=0 +R=3396190`: the published map's sphere and origin with true scale at Jezero, so map metres are ground metres. It is the frame of NASA's own Ingenuity waypoints, so a position here equals NASA's published Easting and Northing.

## Gale walk-area crop pack (P2-01)

`REDMARK_DATA=~/redmark-data uv run python -m prep.gale.build_pack` cuts every Gale source to the walk area and writes `$REDMARK_DATA/gale/crops/` (the crops, `rover-positions.csv`, overlays and `pack.json`), `sites/gale.yaml`, the Gale entries in `data-manifest.yaml` and copies of the overlays in `gale/evidence/`. It takes about a minute, plus a few minutes the first time to checksum the 50 GB photo map.

- **Walk area.** Set in `gale/walk_area.yaml`, with the reasons for the choice: the habitat sits on flat open ground about 480 m west of Curiosity's boxwork drive, the walk area is the 4 × 4 km square holding the 2 km walk radius, and the crops add 500 m round it. A new walk area is a rerun, not a code change.
- **Sources.** The sources are expected at the top of `REDMARK_DATA` under their published names, as Person 3's horizon grid also reads them. The photo map, terrain and THEMIS are all in the site projection, so each crop is a window on its source's own pixel grid, never resampled. The window is snapped outward to whole pixels, so the 1 m terrain crop starts on its source's half-metre grid.
- **Frame check.** The photo map was made from images taken before Curiosity landed, so it shows no rover tracks to check by eye. The build runs two checks instead and fails if either does. First, the orthophoto and terrain grids that PLACES localised Curiosity on must sit a whole number of pixels from our maps' grids, within 1 cm. Second, the terrain's height at each of Curiosity's stops in the crops must match PLACES' elevation there: the median within 0.5 m, and 9 in 10 stops within 0.5 m. On the boxwork slopes, a sideways shift between the frames would fail this. Results are in `pack.json` under `frame_check`.
- **THEMIS offset, recorded, not corrected.** The build correlates THEMIS thermal inertia with the photo map's brightness and the terrain's slope for every 25 m shift up to 300 m. It records, under `thermal_inertia_offset` in `pack.json`, the best move by each measure and its correlation, with and without the move. The two measures roughly agree on a move of a few THEMIS pixels, but the correlations are weak, so the crop is left as published. P2-03 should read the walkability layer with that uncertainty in mind.
- **Crop extents.** Each crop covers the asked bounds on its own source grid, so the edges differ by up to one source pixel: the terrain crop sits half a metre off the whole metre, and THEMIS reaches 50 m further north and south. Read each crop's own transform.
- **Still to come.** CRISM and Curiosity chemistry join the pack in a follow-up, once downloaded.
