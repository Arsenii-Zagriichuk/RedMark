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

**Walk view (P1-05).** Start walk on a crew route opens `src/walk/WalkScreen.tsx`, a tablet screen that plays `POST /simulate` along the chosen route: the dot with its uncertainty circle and confidence chip (green to 5 m, amber to the 10 m fix request, red beyond), heading to the next checkpoint or the target, time and distance left, the route's planned walk-back margin, and the conditions strip from the sol file (the walk starts at first light; dust says measured or estimated). Play, pause and scrub the run; horizon, ground and drone fixes (H, G, D) and fix requests sit on the timeline. The fix schedule is a horizon fix a third of the way, ground halfway and drone at two thirds (`src/walk/schedule.ts`). The whole screen is labelled "Simulated walk". Demo step: `walk.simulate.<mode>.<target>.<slope>`.
