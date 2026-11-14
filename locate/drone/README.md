# locate/drone/

Owner: Person 2 (data and drone matcher).

The drone matcher at Jezero and the simulated Gale drone fix. Writes to `results/drone/`. Lists the matcher weights it reads in `data-manifest.yaml`.

## First drone fix (P2-05)

```bash
uv sync --group gpu
REDMARK_DATA=~/redmark-data uv run --group gpu python -m locate.drone.first_fix <frame> [--matcher lightglue]
```

`<frame>` is a Navcam product from the Jezero pack's `frames.csv`, without `.IMG`. It needs the Jezero pack (`prep/jezero/build_pack.py`) and JPL's weights: `weights_loftr.zip` from https://huggingface.co/dpisanti/mbl-mars, unzipped into `$REDMARK_DATA/weights/mbl-mars/`. The LightGlue fallback downloads its weights into `$REDMARK_DATA/weights/torch-hub/` on first use.

The steps, one module each:

1. `label.py` reads the frame's CAHVORE camera and onboard pose from its PDS label. The take-off point is the previous flight's landing waypoint from NASA.
2. `ground.py` straightens the fisheye onto flat ground at the map's 25 cm, north up, and cuts the map window: 60 m around the drone's onboard position plus the view's reach.
3. `fix.py` matches the view against overlapping tiles of the window, the size of the view, as JPL's pipeline does. It then fits a similarity with RANSAC: the nadir carried onto the map is the position, and the onboard heading turned by the fit is the heading.
4. `matchers.py`: LoFTR with JPL's fine-tuned weights is the matcher of record; DISK with LightGlue is the drop-in fallback.

Time per fix covers reading the frame to fitting the fix; it leaves out loading the matcher's weights and drawing the overlay.

`first_fix.py` writes `results/drone/fixes/<frame>.json` (LoFTR only) and an overlay per matcher in `results/drone/overlays/<frame>-<matcher>.png`. In the overlay, photo and map alternate in 4 m squares inside the photo's outline; where the fit is right, rocks and ridges run on across the squares' edges.

Until P2-06 measures them on the answer key, every drone fix carries an uncertainty circle of 10 m (the project's drone target) and a confidence of 0%, as named constants in `fix.py`.

Tests: `uv run pytest locate/drone`. They need no GPU or data. The end-to-end test scores a fix against its own key through the shared scorer and expects zero error.
