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
