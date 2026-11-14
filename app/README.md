# app/

Owner: Person 1 (app, service shell and submission).

The React app (Vite, strict TypeScript): the 8 key screens.

**Reaching the service.** Only through `src/api/client.ts`; `npm run lint` (oxlint) fails on `fetch` anywhere else, so demo mode can't be bypassed. Screens get the client from `useApi()` (`src/api/ApiContext.tsx`), and every call names its demo step, such as `client.route("planning.route.fastest", request)`.

- **Live mode** calls the service at `VITE_SERVICE_URL` (default `http://127.0.0.1:8000`).
- **Demo mode** answers every step from `cache/demo/`, bundled into the app at build time, with the network off and the service down. A step that isn't in the cache, or was recorded for a different request, fails loudly.
- The switch at the top of the app moves between them, and the choice survives a reload.

```bash
npm run dev --prefix app        # the app
npm test --prefix app           # the API client tests (vitest)
npm run lint --prefix app       # oxlint
```

**Plan screen map (P1-03).** `src/plan/PlanScreen.tsx` loads the site config, layer files and replayed sol (demo steps `plan.site`, `plan.layers`, `plan.conditions`) and draws them with deck.gl in local metres (`src/map/`): the base photo map and one colour layer as tiles, chosen per zoom from each `layer.json`; habitat, base camp, science targets and checkpoints; the 2 km walk limit; and pan, zoom, north-up and 3D tilt. Draping on 3D terrain waits for an elevation layer from Person 2. Restart `npm run dev` after recording new demo steps, so demo mode bundles them.

**Planning (P1-04).** A science target's place card opens Directions (`src/plan/Directions.tsx`): the fastest safe route and the science alternative from base camp to the target, and the cart's trip from the habitat to base camp, each from `POST /route`. The chosen route shows its total time, walk-back margin and all seven walk limits as pass, fail or not checked (a limit the engine didn't return). The 20°/15° slope limit re-plans all three. Demo steps: `plan.route.<mode>.<target>.<slope>` and `plan.route.cart.<slope>`.

**Walk view (P1-05).** Start walk on a crew route opens `src/walk/WalkScreen.tsx`, a tablet screen that plays `POST /simulate` along the chosen route: the dot with its uncertainty circle and confidence chip (green to 5 m, amber to the 10 m fix request, red beyond), heading to the next checkpoint or the target, time and distance left, the route's planned walk-back margin, and the conditions strip from the sol file (the walk starts at first light; dust says measured or estimated). Play, pause and scrub the run; horizon, ground and drone fixes (H, G, D) and fix requests sit on the timeline. The fix schedule is a horizon fix a third of the way, ground halfway and drone at two thirds (`src/walk/schedule.ts`). The whole screen is labelled "Simulated walk". Demo step: `walk.simulate.normal.<mode>.<target>.<slope>`.

**Simulation controls and Lost mode (P1-07).** The break-it buttons (Camera off, Radio off, Drone grounded, Everything) re-run the same walk with those sources off (`src/walk/schedule.ts`), carrying on from the same time; a lit button goes back to the normal walk. Badges follow the project document's backup table (`src/walk/breakIt.ts`): "Camera off", "Offline mode", "Lost mode"; a fix that can't reach the crew is greyed out on the timeline. Once the run switches to lost mode, `src/walk/lost.ts` gives the last known position, re-plans the walk back with `POST /route` (the circle as hazard margin, the walk time left as limit), and words layer 5's landmarks for the walk back, by Person 3's rule in `layers/location_quality/directions.py`, from `layer5-<site>.json` and `landmarks.yaml` (bundled by `src/walk/layer5.ts`). Demo steps: `walk.simulate.<scenario>.<mode>.<target>.<slope>` and `walk.route.back.<scenario>.<mode>.<target>.<slope>`. The demo walk (fastest to `sw-ridge`, 20°) is recorded for every scenario: re-record its runs whenever its cached route changes.

**Test lab (P1-06).** "Test lab" in the Plan sidebar footer opens `src/lab/LabScreen.tsx`: each test summary's share within 1, 5 and 10 m and median error, overall and for textured and plain ground, with JPL's benchmark from `pitch/benchmarks.json` (cited; ticks on the drone test's bars); and the tested photos built from the fix results (those with an answer key). Pick a photo for its overlay, its fix and true position on the map and its error (plus heading error for horizon fixes). A simulated summary or fix never appears; a stub summary shows as pending. In live mode the results reload every 15 s. Demo steps: `lab.summaries`, `lab.fixes.<method>`, `lab.site.<site>`, `lab.layers.<site>`.
