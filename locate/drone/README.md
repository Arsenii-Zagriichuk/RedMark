# locate/drone/

Owner: Person 2 (data and drone matcher).

The drone matcher at Jezero and the simulated Gale drone fix. Writes to `results/drone/`. Lists the matcher weights it reads in `data-manifest.yaml`.

## First drone fix (P2-05)

```bash
uv sync --group gpu
REDMARK_DATA=~/redmark-data uv run --group gpu python -m locate.drone.first_fix <frame> [--previous <earlier-frame>] [--matcher lightglue]
```

`<frame>` is a Navcam product from the Jezero pack's `frames.csv`, without `.IMG`. It needs the Jezero pack (`prep/jezero/build_pack.py`) and JPL's weights: `weights_loftr.zip` from https://huggingface.co/dpisanti/mbl-mars, unzipped into `$REDMARK_DATA/weights/mbl-mars/`. The LightGlue fallback downloads its weights into `$REDMARK_DATA/weights/torch-hub/` on first use.

For a later frame of the same flight, pass `--previous <frame fixed before it>`: the search is then centred on that fix, moved by how far the drone thinks it flew since. The onboard position alone only starts a flight's first fix. Nothing is written unless the code that makes the fix (`locate/drone`, `prep`, `contracts`, the lock files) is committed.

The steps, one module each:

1. `label.py` reads the frame's CAHVORE camera and onboard pose from its PDS label. The take-off point is the previous flight's landing waypoint from NASA.
2. `ground.py` straightens the fisheye onto flat ground at the map's 25 cm, north up, and cuts the map window 60 m around the search centre plus the view's reach.
3. `pipeline.py` picks the search centre and chains the steps; `fix.py` matches the view against overlapping tiles of the window, the size of the view, as JPL's pipeline does. It then fits a similarity with RANSAC: the nadir carried onto the map is the position, and the onboard heading turned by the fit is the heading.
4. `matchers.py`: LoFTR with JPL's fine-tuned weights is the matcher of record; DISK with LightGlue is the drop-in fallback.

Time per fix covers reading the frame to fitting the fix; it leaves out loading the matcher's weights and drawing the overlay.

`first_fix.py` writes each run's overlay to `results/drone/overlays/<frame>-<matcher>-<run-id>.png` before publishing the fix to `results/drone/fixes/<frame>.json`. In the overlay, photo and map alternate in 4 m squares inside the photo's outline. Where the fit is right, rocks and ridges run on across the squares' edges.
Each PNG embeds its own schema-valid `fix_result` JSON with input checksums,
plus `matches` and `inliers` metadata. A LightGlue fix can seed `--previous`
the same way a LoFTR fix can. Run the preferred matcher last when comparing
both on the same frame so its result is the one read from `fixes/`.

Every drone fix carries an uncertainty circle of 10 m (the project's drone target) and a confidence of 0%, as named constants in `fix.py`. They are not fitted to the answer key, since the key is the test; the drone test reports how often the 10 m circle holds the truth. What other owners need to know before they use the results is in `results/drone/README.md`.

## Drone test at Jezero (P2-06)

```bash
REDMARK_DATA=~/redmark-data uv run --group gpu python -m locate.drone.score_jezero [--matcher lightglue]
```

Runs the matcher on every frame of Person 4's answer key (P4-01, read with `route.answer_key.read_answer_key`) and scores each fix through the shared scorer. It needs the Jezero pack, the PDS labels, JPL's weights and `$REDMARK_DATA/jezero/answer-key/` (`keys/`, `overlays/`, `flights.json`).

- **Order and search.** Each flight's keyed frames run in time order. A flight's first frame is searched around the onboard position; each later one around the previous fix, moved as the drone thinks it moved since (as in `first_fix.py`).
- **No lock.** A frame the matcher cannot lock on (fewer than 15 matches agree) gets a fix at its search centre, the position the crew would still have, and it is scored. A miss counts against the numbers rather than dropping out. Its overlay says NO LOCK.
- **Tuning flight.** P2-05 chose the tiling and match limits on flight 10's frames, so flight 10 is the tuning flight (`TUNING_FLIGHTS`): a key on it is refused. The flights share airfields, so a key whose ground a flight 10 frame may have seen is also left out and listed in the output. The check uses each frame's reach (how far its straightened view sees, 35–45 m) plus 20 m for flight 10's onboard positions drifting. On the pack this leaves 20 frames that can be keyed: flight 9's first 8, flight 11's last 6 and flight 15's first 6.
- **Output.** A scored fix result per frame in `results/drone/fixes/<frame>.json` (with `truth`), its overlay in `results/drone/overlays/<frame>-<matcher>-<run-id>.png`, and the test summary `results/drone/drone-jezero.json`: median error and the share within 1, 5 and 10 m, overall, by terrain type (Person 4's by-eye tags) and for hard mode (sand ripples, `hard_mode`). The run prints JPL's benchmark beside them: 89.4% within 5 m and 99.8% within 10 m. Like `first_fix.py`, nothing is written unless the fix code and `route/answer_key.py` are committed.
- **Overlay.** As in P2-05, plus the answer key's position as a magenta cross, and the error in the title.

## Simulated Gale drone fix (P2-07)

```bash
REDMARK_DATA=~/redmark-data uv run --group gpu python -m locate.drone.gale_fix [--matcher lightglue]
```

There are no drone photos of Gale, so `gale_view.py` cuts one from the Gale 25 cm photo map: drawn at 5 cm per pixel (about Ingenuity's Navcam from 10 m), up being the drone's heading, with each astronaut's suit markers drawn in (orange helmet ahead, green backpack behind). `gale_fix.py` places the crew on the demo walk (Person 4's fastest route from base camp to the first science target at the app's default limits, where the crew is when the app's walk schedule fires the drone fix: two thirds of the route's length at the 2 km/h planning speed, the clock `app/src/walk/schedule.ts` and `sim/engine.py` both walk by, not the legs' slope-aware times), with the drone hovering 8 m behind them. The photo then goes through the real pipeline: straightened north up at 25 cm by an onboard heading 3° off, searched around an onboard position 7.9 m off, matched with LoFTR and JPL's weights, and fitted. The astronaut detection mock-up finds the markers by colour, pairs each helmet with the nearest backpack, and carries both onto the map through the fit; the crew's fix is the astronauts' midpoint, facing their mean heading.

The photo comes from the same map it is matched to, so it shows the pipeline, not accuracy. The fix result has `simulated: true` and `truth: null`, every image carries a SIMULATED banner, and no error is computed. Needs the code committed, like `first_fix.py`. It stops if the fix lands outside the site or more than 5 m off the route, and prints the demo step whose cached route the fix sits on (`plan.route.fastest.<target>.20`): that entry must be recorded from the same site config and route engine (`prep/gale/demo_cache.py`), or the Drone fix screen shows the crew off the walk. Its provenance lists the route engine's inputs as well: the slope, sand and ridge layers, the conditions file and, when it exists, Person 3's layer 5 checkpoint candidates. What it writes is in `results/drone/README.md`.

Tests: `uv run pytest locate/drone`. They need no GPU or data. The drone test's tests run the fixture frame through the whole test to a summary, score a no-lock frame at its search centre, and check that Person 4's tie-point fit, given the matcher's own points, finds the matcher's position and heading. One end-to-end test uses a frozen synthetic frame rendered by NASA VICAR from the flight 10 label and runs straightening, window selection, matching and the shared scorer. Another scores a fix against its own key and expects zero error. The Gale tests cut a photo from a synthetic map and expect the fix back where it was cut and the suit markers back on the astronauts' map positions.
