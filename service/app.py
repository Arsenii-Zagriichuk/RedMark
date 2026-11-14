"""The local service the app talks to (P1-02). Run: `uv run uvicorn service.app:app --reload`.

It serves the contract files (site configs, layers and their tiles, conditions, fix results, test
summaries, overlay images) and forwards route and simulation requests to Person 4's
engines. An engine plugs in by existing: `route/engine.py` with `plan(request: dict) ->
dict` and `sim/engine.py` with `simulate(request: dict) -> dict`. Until then the stub
answers. Both sides of every request are checked against their contracts.

With REDMARK_RECORD=1, every call the app tags with an `X-Demo-Step` header is saved to
`cache/demo/<first path segment>/<step>.json`, which the app's demo mode replays.
"""

import importlib
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool

from contracts.models.route_request import RouteRequest
from contracts.models.route_response import RouteResponse
from contracts.models.simulate_request import SimulateRequest
from contracts.models.simulate_response import SimulateResponse
from contracts.paths import REPO_ROOT, data_root

PLAIN_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
OVERLAY_FOLDERS = ("results", "contracts/stubs/overlays")
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
STUBS = REPO_ROOT / "contracts" / "stubs"
# The fix methods in contracts/schemas/common.json: each may have no fix results yet.
METHODS = {"horizon", "ground", "drone"}


@dataclass(frozen=True)
class Settings:
    repo_root: Path = REPO_ROOT
    data_root: Path = field(default_factory=data_root)
    record: bool = False
    route_engine: str = "route.engine"
    sim_engine: str = "sim.engine"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(record=os.environ.get("REDMARK_RECORD") == "1")


def _name(value: str) -> str:
    """A path segment from the URL; anything that isn't a plain file name is not found."""
    if not PLAIN_NAME.fullmatch(value):
        raise HTTPException(404, f"no such item: {value!r}")
    return value


def _inside(base: Path, relative: str) -> Path:
    """A file under base, refusing any path that climbs out of it."""
    path = (base / relative).resolve()
    if not path.is_relative_to(base.resolve()) or not path.is_file():
        raise HTTPException(404, f"no such file: {relative}")
    return path


def _load(path: Path) -> Any:
    if not path.is_file():
        raise HTTPException(404, f"no such file: {path.name}")
    return json.loads(path.read_text())


def _list(folder: Path, pattern: str) -> list[Any]:
    return [json.loads(path.read_text()) for path in sorted(folder.glob(pattern))]


def _engine(module_name: str, function: str) -> Callable[[dict], dict] | None:
    """Person 4's engine function, or None while its module doesn't exist yet."""
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as error:
        missing = error.name or ""
        if module_name == missing or module_name.startswith(f"{missing}."):
            return None
        raise
    if not callable(getattr(module, function, None)):
        raise HTTPException(502, f"{module_name} exists but has no {function}(request) function")
    return getattr(module, function)


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="RedMark service")
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Demo-Step"],
    )
    root, results = settings.repo_root, settings.repo_root / "results"

    def respond(request: Request, body: Any, payload: Any, contract: str | None) -> JSONResponse:
        step = request.headers.get("X-Demo-Step")
        if step is not None and not PLAIN_NAME.fullmatch(step):
            raise HTTPException(400, f"X-Demo-Step must be a plain step id, got {step!r}")
        if settings.record and step:
            producer = request.url.path.strip("/").split("/")[0]
            path = request.url.path + (f"?{request.url.query}" if request.url.query else "")
            entry = {
                "step": step,
                "request": {"method": request.method, "path": path, "body": body},
                "status": 200,
                "contract": contract,
                "response": payload,
            }
            target = root / "cache" / "demo" / producer / f"{step.replace('.', '-')}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(entry, indent=2) + "\n")
        return JSONResponse(payload)

    async def forward(
        request: Request,
        engine: tuple[str, str],
        contracts: tuple[type[BaseModel], type[BaseModel]],
        stub: str,
        contract: str,
    ) -> JSONResponse:
        body = await request.json()
        request_model, response_model = contracts
        try:
            request_model.model_validate(body)
        except ValidationError as error:
            raise HTTPException(422, json.loads(error.json())) from error
        run = _engine(*engine)
        answer = await run_in_threadpool(run, body) if run else _load(STUBS / stub)
        try:
            response_model.model_validate(answer)
        except ValidationError as error:
            detail = f"{engine[0]} broke the {contract} contract: {error}"
            raise HTTPException(502, detail) from error
        return respond(request, body, answer, contract)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/layers/{site}")
    def layers(request: Request, site: str) -> JSONResponse:
        folder = settings.data_root / _name(site) / "layers"
        found = _list(folder, "*/layer.json")
        if not found:
            raise HTTPException(404, f"no layers for {site}")
        return respond(request, None, found, None)

    @app.get("/layers/{site}/{name}/{file:path}")
    def layer_file(site: str, name: str, file: str) -> FileResponse:
        folder = settings.data_root / _name(site) / "layers" / _name(name)
        return FileResponse(_inside(folder, file))

    @app.get("/sites/{site}")
    def site_config(request: Request, site: str) -> JSONResponse:
        path = root / "sites" / f"{_name(site)}.yaml"
        if not path.is_file():
            raise HTTPException(404, f"no site config for {site}")
        return respond(request, None, yaml.safe_load(path.read_text()), "site")

    @app.get("/conditions/{sol}")
    def conditions(request: Request, sol: str) -> JSONResponse:
        payload = _load(root / "conditions" / f"{_name(sol)}.json")
        return respond(request, None, payload, "conditions")

    @app.get("/fixes/{method}")
    def fixes(request: Request, method: str) -> JSONResponse:
        if method not in METHODS:
            raise HTTPException(404, f"no fix method {method!r}")
        found = _list(results / method / "fixes", "*.json")
        return respond(request, None, found, None)

    @app.get("/fixes/{method}/{photo_id}")
    def fix(request: Request, method: str, photo_id: str) -> JSONResponse:
        payload = _load(results / _name(method) / "fixes" / f"{_name(photo_id)}.json")
        return respond(request, None, payload, "fix_result")

    @app.get("/summaries")
    def summaries(request: Request) -> JSONResponse:
        found = _list(results, "*/*.json")
        return respond(request, None, found, None)

    @app.get("/summaries/{method}/{test}")
    def summary(request: Request, method: str, test: str) -> JSONResponse:
        payload = _load(results / _name(method) / f"{_name(test)}.json")
        return respond(request, None, payload, "test_summary")

    @app.get("/overlays/{file:path}")
    def overlay(file: str) -> FileResponse:
        allowed = any(file.startswith(f"{folder}/") for folder in OVERLAY_FOLDERS)
        if not allowed or Path(file).suffix.lower() not in IMAGE_SUFFIXES:
            raise HTTPException(404, f"no overlay image: {file}")
        return FileResponse(_inside(root, file))

    @app.post("/route")
    async def route(request: Request) -> JSONResponse:
        return await forward(
            request,
            (settings.route_engine, "plan"),
            (RouteRequest, RouteResponse),
            "route/response.json",
            "route_response",
        )

    @app.post("/simulate")
    async def simulate(request: Request) -> JSONResponse:
        return await forward(
            request,
            (settings.sim_engine, "simulate"),
            (SimulateRequest, SimulateResponse),
            "simulate/response.json",
            "simulate_response",
        )

    return app


app = create_app(Settings.from_env())
