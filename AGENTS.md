# RedMark agent guide

RedMark is a layered Mars walk map that finds the crew's position from photos, built by four people and their agents in 24 hours for NASA Space Apps 2026. Read this file first, then the ticket you were given. Words like fix, heading, uncertainty circle and hidden pile have one meaning each, set in [GLOSSARY.md](GLOSSARY.md); use those words in code, tests and issues.

The plan documents in [docs/](docs/) are the brief: the [team plan](docs/team-plan.md) (it wins where documents disagree), the [project document](docs/project-document.md), and one plan per person ([1 app](docs/person-1-app.md), [2 data and drone](docs/person-2-data-drone.md), [3 horizon](docs/person-3-horizon.md), [4 route and simulation](docs/person-4-route-sim.md)). Your person's plan lists your ticket's **test seams**. From H0, a ticket's live status is its GitHub issue, not the plan file.

## Folder owners

Work only inside your owner's folders. Each folder's README names its owner.

| Person | Folders |
| --- | --- |
| 1 · App, service shell and submission | `app/`, `service/`, `pitch/`, `tools/`, `tests/`, `docs/` and the repo root (this file, CI, lock files, `.claude/`) |
| 2 · Data and drone matcher | `prep/`, `sites/`, `locate/drone/` |
| 3 · Horizon matcher and location quality | `locate/horizon/`, `locate/ground/`, `layers/location_quality/`, `contracts/scoring/` |
| 4 · Route and simulation | `route/`, `sim/`, `conditions/` |
| Shared | `contracts/` (a change is one pull request both sides approve); `results/` and `cache/` (each producer writes only its own subfolder) |

## Contracts

The 9 contracts between the parts are JSON Schemas in [contracts/schemas/](contracts/schemas/): site config, layer files, route API, fix result, the shared scorer (code in `contracts/scoring/`), test summary, walk simulation API, conditions, and the demo cache. [contracts/README.md](contracts/README.md) gives each one's producer, file paths and due hour, and how to change it. Read it before you produce or consume any contract file.

- The schemas are the single source. The Python models (`contracts/models/`) and TypeScript types (`contracts/types/`) are generated from them with `uv run python -m tools.gen_contracts`.
- Every contract has a stub at its real path, so nobody waits for real data. Swapping a stub for the real file needs no code change.
- All positions are metres in the site map's own projection. Errors and distances are ground metres.

## Data

`data/` and big map formats (`*.tif`, `*.cub`, `*.img`, `*.jp2`) never go into git. The data folder's location comes from the `REDMARK_DATA` setting, so every worktree reads the same copy; unset, it falls back to the stub data in `contracts/stubs/stub-data/`. Every external file you use goes in your folder's `data-manifest.yaml`, which feeds the project page's References.

## Rules and the checks behind them

1. **Your own worktree and branch.** One agent per checkout: `git worktree add ../redmark-p3-02 -b feat/p3-02-first-horizon-fix origin/main`. Stage files by name. *(Enforced by the git session guard, P1-15.)*
2. **Stay in your owner's folders.** *(Owner-guard hook and CI, P1-15.)*
3. **Stubs first.** Every contract file validates against its schema. *(The smoke test.)*
4. **Merge to main at least every 2 hours**, through a pull request with green CI. Main always passes the smoke test. *(CI and branch protection, P1-15.)*
5. **Every number traces to a script.** Numbers in the app, the slides and the project page come from results files (fix results, test summaries, conditions), and each records the script, commit and input checksums that wrote it in `provenance`. A stub has `provenance.script: "stub"` and is never shown as a real result. *(`provenance` is required by those schemas.)*
6. **Hidden piles stay hidden.** Only the scoring scripts read a hidden-pile folder. *(A test, P3.)*
7. **Map work is checked by eye.** Every crop, layer and match writes an overlay image on the base map, and it goes in the pull request's Evidence section.
8. **Simulated results carry the label.** `simulated` is required with no default, and the app shows every fix through one component that prints the label.

**The checks (P1-15).** CI (`.github/workflows/ci.yml`) runs on every pull request to main: one owner per pull request (`tools/owners.py`, which holds the folder table above), no file over 5 MB, ruff, contract files, generated types, typecheck, app build and every test. `pyproject.toml`, `uv.lock`, `cache/` and `contracts/` are shared: they may come with one owner's change, and a pull request that changes `contracts/schemas/` is a contract change, which may touch both sides. Changes to `contracts/` and the repo root need a code owner's review (`.github/CODEOWNERS`); everything else merges on green CI. The Claude Code hooks in `.claude/settings.json` (they need `jq` and `uv` on your PATH) are the git session guard, the owner guard and formatting on edit. **Set your person number once per clone**, and every worktree reads it: `git config redmark.person <1-4>`.

## The ticket cycle

Every ticket runs the loop in the [team plan](docs/team-plan.md#the-ticket-cycle-matt-pococks-skills): claim the issue, branch `<type>/<ticket>-<slug>` in a worktree, `/implement <issue>` (it agrees the seams with you, builds with `tdd` at those seams, then runs `code-review`), and open a pull request with the `pr` skill (Summary, Evidence, Merge danger, `Closes #<issue>`). Commits are `type: description (#<issue>)`. The owner squash-merges once CI is green and the overlay has been looked at.

Reviews check [CODING_STANDARDS.md](CODING_STANDARDS.md) (the Standards axis) and the issue (the Spec axis).

## Commands

```bash
uv sync                                    # Python 3.11 env; Person 2 adds --group gpu for PyTorch
npm ci --prefix app                        # app dependencies (Node 22 LTS)
uv run pytest tests/smoke                  # the smoke test: contracts, service, app build
uv run pytest                              # every test
uv run python -m tools.check_contracts     # just the contract files
uv run python -m tools.gen_contracts       # regenerate models and types after a schema change
uv run ruff check . && uv run ruff format --check .
npm run typecheck --prefix app
npm run lint --prefix app && npm test --prefix app   # app lint (fetch only in the API client) and tests
uv run python -m tools.owners check        # does this branch stay in one owner's folders?
uv run uvicorn service.app:app --reload    # the service; REDMARK_RECORD=1 records the demo cache
npm run dev --prefix app                   # the app
```

## Agent skills

### Issue tracker

GitHub Issues on this repo, through the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The default five: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` at the root, decisions in `docs/adr/`. See `docs/agents/domain.md`.
