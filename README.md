# RedMark

A layered Mars walk map that finds the crew's position from photos instead of satellites. NASA Space Apps 2026, challenge [Interplanetary Survival Guide: Martian Map](https://www.spaceappschallenge.org/2026/challenges/interplanetary-survival-guide-martian-map/).

Start with [AGENTS.md](AGENTS.md) (folder owners, contracts, rules, commands) and the [team plan](docs/team-plan.md).

## Setup

Needs [uv](https://docs.astral.sh/uv/) and Node 22 LTS.

```bash
uv sync
npm ci --prefix app
uv run pytest tests/smoke
```

Point `REDMARK_DATA` at the shared data folder (crops and layers from Person 2). Unset, the stub data in `contracts/stubs/stub-data/` is used.
