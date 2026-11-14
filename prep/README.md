# prep/

Owner: Person 2 (data and drone matcher).

Crops, reprojection, tiles and layer files for layers 1 to 3; the Jezero pack. Lists its data files in `data-manifest.yaml`.

## Jezero pack (P2-04)

`REDMARK_DATA=~/redmark-data uv run python -m prep.jezero.build_pack` builds the pack Person 4 keys the drone answer key on. Flights and margins are in `jezero/pack.yaml`. It writes `$REDMARK_DATA/jezero/pack/` (crops, frame images, overlays, `frames.csv`), `sites/jezero.yaml` and the Jezero entries in `data-manifest.yaml`.

Every Jezero position is in the site frame `+proj=eqc +lat_ts=18.4663 +lon_0=0 +R=3396190`: the published map's sphere and origin with true scale at Jezero, so map metres are ground metres. It is the frame of NASA's own Ingenuity waypoints, so a position here equals NASA's published Easting and Northing.
