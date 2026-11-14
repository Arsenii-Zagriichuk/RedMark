# locate/ground/

Owner: Person 3 (horizon matcher and location quality).

The stage 2 ground-fix attempt at Gale (P3-07). Writes to `results/ground/`.

## How it works

Curiosity's Navcam mosaic archive already holds the overhead view stage 2 needs: a **VRT** (vertical) mosaic at most stops, made from the stop's Navcam frames projected straight down onto a plane fitted to the ground. Each is 4800 × 4800 pixels of 5 mm (24 m across), centred on the rover, north-up. 213 of them sit at stops inside the walk area (sites 105 to 121, sols 4037 to 4865). So no stereo reconstruction is built here.

1. **Overhead view** (`mosaic.py`): the mosaic averaged into the photo map's 25 cm cells (96 × 96). Cells that saw nothing, and everything within 3 m of the rover (its deck, wheels and shadow), are masked out.
2. **Search window** (`pile.py`): the photo map within ±60 m of the rover's PLACES position, standing in for the stage 1 prior. It is read from the site's photo-map crop when that is in `REDMARK_DATA`, otherwise a window at a time straight from the full 25 cm USGS file over HTTP (about 30 s a window).
3. **Match** (`match.py`): both images high-passed at 4 m, then masked normalised cross-correlation at every placement; the best peak is the fix. Its heading is the rover's onboard heading from a source frame's label, since the view is north-up by that attitude. The circle's radius is taken from the search, not measured: the window's half-width, 60 m. The window is a square, so its corners reach about 85 m and a fix can land outside the circle.

**Where it runs.** The match takes 0.02 s per stop on a laptop CPU and the photo map is read over HTTP, so all of it runs on Person 3's machine. Person 2's GPU batches (P2-08) aren't needed.

## Piles

| Pile | Folder in `REDMARK_DATA` | Stops | Command |
| --- | --- | --- | --- |
| Tuning | `gale/ground/tuning` | 7, spread over sites 105 to 119 (`tune.py`'s `TUNING_STOPS`) | `uv run python -m locate.ground.tune` |
| Hidden | the hidden-pile folder named in `hidden_pile.py` | 40, evenly along the traverse by sol, none whose view shares ground with a tuning stop's (views are 24 m north-up squares, so a held-out stop must be at least 24 m from every tuning stop east-west or north-south, not just 24 m away) | `uv run python -m locate.ground.hidden_pile`, then `uv run python -m locate.ground.hidden_test` |

Each pile folder holds, per stop, the mosaic's label, its first source frame's label, and an `.npz` with the view, mask and search window. The 46 MB mosaic image is deleted once its view is saved; `index.csv` keeps its checksum and URL. Only `hidden_pile.py` and `hidden_test.py` name the hidden folder (`locate/horizon/tests/test_hidden_pile_isolation.py`).

## Tuning

`tune.py` tries five high-pass scales on the tuning pile. Errors in metres from PLACES:

| Stop (site, drive) | 0.5 m | 1 m | 2 m | 4 m | 8 m |
| --- | --- | --- | --- | --- | --- |
| 105, 1108 | 35.3 | 44.1 | 44.1 | 17.6 | 58.4 |
| 111, 2386 | 21.1 | 23.0 | 38.9 | 45.2 | 45.6 |
| 114, 534 | 23.1 | 23.1 | 20.1 | 20.1 | 27.0 |
| 116, 408 | 45.0 | 15.9 | 38.0 | 22.7 | 22.7 |
| 117, 2370 | 32.1 | 34.1 | 33.9 | 3.7 | 42.9 |
| 117, 2730 | 29.5 | 42.0 | 18.7 | 0.2 | 34.0 |
| 119, 486 | 45.8 | 40.1 | 0.3 | 0.3 | 0.3 |
| **Within 5 m** | 0/7 | 0/7 | 1/7 | **3/7** | 1/7 |

4 m it is. A miss lands anywhere in the window (a random spot in it is about 35 m out on average), so the matcher either finds the rover to within a few metres or not at all. Overlay: `overlays/p3-07-tuning.png`.

## Held-out result and the H12 call

`hidden_test.py` on the 40 held-out stops, through the shared scorer: `results/ground/ground-gale-attempt.json` (measured, `simulated: false`), a fix result per stop in `results/ground/fixes/`, and overlays in `results/ground/overlays/` (`p3-07-held-out.png` has every stop on one sheet).

| | Stops | Within 1 m | Within 5 m | Median error |
| --- | --- | --- | --- | --- |
| All | 40 | 30.0% | 32.5% | 22.0 m |
| Textured ground | 27 | 29.6% | 33.3% | 25.0 m |
| Plain ground | 13 | 30.8% | 30.8% | 21.2 m |

**Call at H12: no-go.** 32.5% within 5 m is below the 50% bar, so stage 2 stays simulated and labelled (P3-08). It fails in a telling way: 12 of the 13 hits are sub-metre (0.1 to 0.7 m, and one at 1.2 m), the precision JPL reports for this method, and every miss is 13.5 to 62.7 m out, somewhere else in the window. The matcher finds the rover precisely or not at all, and it can't yet tell which.

Two numbers in the summary are not measurements. The heading error is 0.0° because the ground fix carries the rover's onboard heading, which is the same yaw PLACES gives at these stops. The circle is the search half-width (60 m), not a fitted uncertainty: 37 of 40 fixes (92.5%) fall inside it, and three misses (60.2, 61.9 and 62.7 m) land in the window's corners beyond it.

A first run held out stops more than 24 m from every tuning stop by centre distance. That let one held-out view (site 119, drive 198) overlap a tuning view by 1.1 × 11 m on the diagonal, so the selection now checks the squares themselves (`locate/ground/tests/test_held_out.py`). With that stop out, the even spacing picked 11 different stops; the table above is the rerun on the new 40. That first run gave the same call (32.5% within 5 m; 30.8% without the overlapping stop).

These 40 stops have now been matched, and so have the 11 the first selection held out and the second dropped (`index.csv` lists the 40; the 11 are the other `.npz` files in the hidden folder). Any tuning from here uses the tuning pile only, or walk-area stops that are in neither selection, or the next score on the hidden pile means nothing.

## Next: make the matcher better

The go bar is 50% of held-out fixes within 5 m (`hidden_test.py`'s `GO_WITHIN_5M_PCT`); the attempt reached 32.5%. Getting the share as high as it will go is a follow-up for a separate session on Fable, tuned on the tuning pile only and scored once on the hidden pile. Leads seen in the overlays:

- The rover's mast and arm stick out past the 3 m mask as bright streaks; mask them, such as by brightness or by the rover's footprint from the label.
- Brightness steps between the mosaic's frames, and shading that changes with the time of day, against the orbiter's single lighting; try gradient-orientation or rank features instead of a plain high-pass.
- Only 24 m of ground per view. Neighbouring stops' mosaics could be joined by the rover's own drive record to see more ground.
- The search window is ±60 m; a sharper stage 1 prior or a peak test (peak against runner-up) could reject the misses rather than report them.
