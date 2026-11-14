# layers/location_quality/

Owner: Person 3 (horizon matcher and location quality).

Layer 5: landmark visibility, the error map, checkpoint candidates and lost-mode landmark directions.

## Landmark visibility (P3-05)

`uv run python -m layers.location_quality.build` works out, for every 1 m cell of the walk area in `sites/gale.yaml`, which of the four landmarks an eye 1.9 m above the ground can see, and combines them into one score: the share of the four in view (0, 0.25, 0.5, 0.75 or 1, every landmark weighing the same). It writes, under `REDMARK_DATA`:

| Output | For | Contents |
| --- | --- | --- |
| `gale/layers/landmark_<id>/` | the app's map (P1) | one layer per landmark: in view or hidden, layer group 5, 1 m |
| `gale/layers/location_quality/` | the app's map (P1) | the combined score, five legend classes |
| `gale/rasters/location_quality.tif` | the route (P4) | the score as one float32 band in the site projection, 1 m |

Each layer folder is `layer.json` plus PNG tiles in the layer contract (`contracts/schemas/layer.json`): at the finest zoom one pixel is one 1 m cell, and each lower zoom halves that, down to one tile. The route reads rasters named under `files` in the site config, so using the score there needs a `location_quality: gale/rasters/location_quality.tif` key in `sites/gale.yaml` (Person 2's file) when P4-07 starts.

The run also writes `layer5-gale.json` here (the landmark points found, the share of the walk area that sees each, the spot check, computing time, and the script, commit and input checksums) and the overlay `overlays/p3-05-layer5.png`.

- **Line of sight** (`visibility.py`): over the same terrain as the horizon grid (the 1 m Gale terrain, its 10 m copy, and the HRSC and MOLA blend beyond), on the Mars sphere. Line of sight is the same both ways, so rays are cast from each landmark point across the walk area, not from each of 16 million cells: along a ray, the running maximum of the elevation angle seen from the point is what a cell's eye has to rise above. Neighbouring rays are under 0.7 of a cell apart at the far edge and each cell reads the nearest one. Ground within a landmark's body radius is the landmark itself and never hides it, or a butte's near edge would hide its own top from anyone looking at the butte.
- **Landmarks** (`landmarks.yaml`, found by `landmarks.py`): no catalogue gives the buttes' positions, so each is found in the terrain, with the reason written next to it. Texoli is the high point at the south-east end of the mesa whose northern tip Curiosity rounded on sols 4391 to 4398. The upper Mount Sharp peak and Mishe Mokwa are the terrain forming the skyline at 98° and 155° from Curiosity's camera at sol 4611 (site 117, drive 2730), where NASA's Navcam mosaic PIA26632 names them. The crater rim is 19 points, the far skyline (15 to 80 km) every 10° from west through north to north-east of the walk area; a cell sees the rim if it sees any of them.
- **Check by eye:** `uv run python -m layers.location_quality.plot_landmark_check` draws those sol 4611 frames with the calculated skyline and a line at each landmark point's heading: `overlays/p3-05-landmarks-sol4611.png`.
- **Spot check:** ridge tops should see more landmarks than hollows near tall ridges. A hollow is a cell more than 1 m below the mean ground within 50 m (the horizon test's rule in `locate/horizon/stop_terrain.py`), a ridge top a cell as far above it; `layer5-gale.json` and the overlay give the mean score of each.

## Layer 5 final (P3-06)

The same run (`uv run python -m layers.location_quality.build`) then adds the error map, turns the score into the final location quality, and picks checkpoint candidates and lost-mode landmark directions. New outputs, under `REDMARK_DATA`:

| Output | For | Contents |
| --- | --- | --- |
| `gale/layers/error_map/` | the app's map (P1) | median horizon fix error for each cell's class, ground metres, three legend classes |
| `gale/rasters/error_map.tif` | the route (P4) | the same, one float32 band, 1 m |

`gale/layers/location_quality/` and `gale/rasters/location_quality.tif` now hold the final score, not only the landmark share.

- **Error map** (`error_map.py`): every cell gets the class a stop there would get in the horizon test, by the test's own rules (`locate/horizon/stop_terrain.py`): a hollow, or else textured or plain ground. It then takes that class's median error from the test summary `results/horizon/horizon-gale.json`. No error number is typed in the code. The test splits by terrain type and by hollow separately, so a hollow takes the hollow median whatever its terrain type: ridges hiding the skyline is the larger effect. Cells are judged on ground that reaches 51 m past the walk area's edge, so edge cells get a full circle too.
- **Score:** the share of landmarks in view times (the lowest class median ÷ the cell's median). It runs from 0 to 1, and 1 means all four landmarks in view from the best-measured class of ground.
- **Checkpoint candidates** (`checkpoints.py`): the walk area is cut into 500 m squares and each square gives its best-scoring cell outside a hollow, so wherever a route goes there are candidates nearby, not only in the north-west corner, the one part that sees all four landmarks. The score takes few values, so ties go to the cell with the better mean score within 10 m, which keeps candidates off the rims of hollows and the map's edge. Each candidate is listed in `layer5-gale.json` with its score, expected error, terrain type and the landmarks in view (heading to each). P4-07 picks among them.
- **Landmark directions** (`directions.py`): for each leg of the demo route (the saved `POST /route` response in `cache/demo/route/planning-route-fastest.json`), every landmark's share of the leg in view and its side, sampled every 10 m against the heading of the path there. The leg's `text` uses the first landmark in `landmarks.yaml`'s order that is in view from at least half the leg:
  - within 30° of the heading: "Walk towards Texoli";
  - 150° or more off: "Keep the Gale crater rim behind you";
  - otherwise "Keep the upper Mount Sharp peak on your left" (or right).

  With no such landmark the leg has no `text`. The crater rim lies at the mean bearing of its points. A re-recorded demo route only needs a rerun.
- **Check by eye:** `overlays/p3-06-layer5-final.png` shows the error map, the score with the candidates and the demo route, and each leg's direction.
