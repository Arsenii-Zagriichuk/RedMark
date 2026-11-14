"""The local service the app talks to. P1-01 shell: it only starts.

P1-02 adds layers, route, simulation, conditions, fix results, test summaries
and the demo cache. Run: `uv run uvicorn service.app:app --reload`.
"""

from fastapi import FastAPI

app = FastAPI(title="RedMark service")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
