from dataclasses import replace
from pathlib import Path
import time

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.main import create_app
from scripts.make_test_pdfs import make_test_pdfs


@pytest.fixture(scope="session")
def samples(tmp_path_factory):
    return make_test_pdfs(tmp_path_factory.mktemp("synthetic-pdfs"))


@pytest.fixture
def client(tmp_path):
    settings = replace(Settings(), workspace=tmp_path / "jobs", allowed_hosts=("testserver",), cleanup_interval=0.1)
    with TestClient(create_app(settings)) as client:
        csrf = client.get("/api/v1/session").json()["csrf_token"]
        client.headers["X-CSRF-Token"] = csrf
        yield client


def submit(client, path: Path, filename: str | None = None, **options):
    return client.post("/api/v1/jobs", files={"file": (filename or path.name, path.read_bytes(), "application/pdf")}, data=options)


def wait_job(client, job_id):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200, response.text
        job = response.json()
        if job["state"] in {"succeeded", "failed", "cancelled"}:
            return job
        time.sleep(0.05)
    raise AssertionError("Job did not finish")
