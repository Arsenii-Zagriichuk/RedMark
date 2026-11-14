# Contracts

Owner: shared. A change to a schema is one pull request that both the producer and the users approve, agreed at H0 or later in 15 minutes. After editing a schema, run `uv run python -m tools.gen_contracts` and commit the regenerated `models/` and `types/` with it.

- `schemas/`: the JSON Schemas, the single source. `common.json` holds shared definitions (point, bounds, provenance).
- `models/`, `types/`: generated Python models (`from contracts.models.fix_result import FixResult`) and TypeScript types (`import type { FixResult } from "@contracts/fix_result"`).
- `registry.yaml`: where each contract's files live; the smoke test checks every file it finds there.
- `stubs/`: stub files for request/response contracts and stub data for `REDMARK_DATA`.
- `scoring/`: the shared scorer (Person 3, P3-09).

| Contract | Schema | Files | Producer | Used by | Real by |
| --- | --- | --- | --- | --- | --- |
| Site config | `site.json` | `sites/<site>.yaml` | 2 (sol from 4) | All | Before H0 |
| Layer files | `layer.json` | `$REDMARK_DATA/<site>/layers/<name>/layer.json` plus tiles | 2 (groups 1 to 3), 3 (group 5) | 1, 4 | Layer 1 H4; 2 and 3 H6; 5 H10, final H14 |
| Route API `POST /route` | `route_request.json`, `route_response.json` | stubs in `stubs/route/` | 4 (engine), served by 1 | 1, 4 | Fastest H8; all H10 |
| Fix result | `fix_result.json` | `results/<method>/fixes/<photo_id>.json` | 2 (drone), 3 (horizon, ground) | 1, 4 | First fixes H6 |
| Scorer | (code) | `contracts/scoring/` | 3 (2 reviews) | 2, 3 | H3 |
| Test summary | `test_summary.json` | `results/<method>/<test>.json` | 2, 3 (through the scorer) | 1, 4 | H12 |
| Walk simulation `POST /simulate` | `simulate_request.json`, `simulate_response.json` | stubs in `stubs/simulate/` | 4 | 1 | H12; break-it H14 |
| Conditions | `conditions.json` | `conditions/<sol>.json` | 4 | 1, 4 | H8 |
| Demo cache | `demo_cache.json` | `cache/demo/<producer>/<step>.json` | each producer | 1 | H16 |

Also checked: `data_manifest.json`, for each owner's `data-manifest.yaml`.

**Open at H0.** What the uncertainty circle and the confidence % mean. The schemas carry the team plan's proposal (the circle is the 95% radius in ground metres; confidence is the share of tested fixes, for that method and terrain type, whose true position fell inside their circle), marked PROPOSED. Every stub value is a placeholder.
