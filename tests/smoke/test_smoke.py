"""The smoke test that main must always pass: `uv run pytest tests/smoke`.

The service starts, the app builds, and every stub, cache and results file
matches its contract.
"""

import shutil
import subprocess

from fastapi.testclient import TestClient

from contracts.paths import REPO_ROOT, data_root
from service.app import app
from tools.check_contracts import check


def test_every_contract_file_matches_its_schema():
    assert check(REPO_ROOT, data_root()) == []


def test_the_service_starts():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_the_app_builds():
    npm = shutil.which("npm")
    assert npm, "npm not found: install Node 22 LTS"
    assert (REPO_ROOT / "app" / "node_modules").is_dir(), "run `npm ci` in app/ first"

    result = subprocess.run(
        [npm, "run", "build"], cwd=REPO_ROOT / "app", capture_output=True, text=True
    )

    assert result.returncode == 0, result.stdout + result.stderr
