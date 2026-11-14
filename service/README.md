# service/

Owner: Person 1 (app, service shell and submission).

The local FastAPI service the app talks to (P1-02). Run it with `uv run uvicorn service.app:app --reload`; it reads layers from `REDMARK_DATA` (the stub data when unset).

| Endpoint | Answers with |
| --- | --- |
| `GET /layers/{site}` | every `layer.json` under `$REDMARK_DATA/<site>/layers/` |
| `GET /layers/{site}/{name}/{file}` | a file in that layer's folder, such as `tiles/{z}/{x}/{y}.png` |
| `GET /conditions/{sol}` | `conditions/<sol>.json` |
| `GET /fixes/{method}`, `GET /fixes/{method}/{photo_id}` | the fix results in `results/<method>/fixes/` |
| `GET /summaries`, `GET /summaries/{method}/{test}` | the test summaries `results/<method>/<test>.json` |
| `GET /overlays/{path}` | an overlay image by its repo path (under `results/` or `contracts/stubs/overlays/`) |
| `POST /route`, `POST /simulate` | Person 4's engines, or the stub until they exist |

**Plugging in an engine (Person 4).** Create `route/engine.py` with `plan(request: dict) -> dict`, and `sim/engine.py` with `simulate(request: dict) -> dict`. The service needs no change: it uses the module as soon as it exists. Requests are checked against `route_request` / `simulate_request` before the engine runs (422 if they break it), and answers against `route_response` / `simulate_response` (502 if they break it).

**Recording the demo cache.** Start the service with `REDMARK_RECORD=1`. Every call the app tags with an `X-Demo-Step` header (the API client always does) is saved to `cache/demo/<first path segment>/<step>.json`, which the app's demo mode replays. Click through the demo in live mode once, then commit the files.
