import json
import tomllib

from fastapi.testclient import TestClient

from app.config import APP_VERSION, PROJECT_ROOT


def test_manifest_versions_match_app_version():
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package = json.loads((PROJECT_ROOT / "package.json").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == APP_VERSION
    assert package["version"] == APP_VERSION


def test_health_and_app_report_app_version(client: TestClient):
    assert client.app.version == APP_VERSION
    assert client.get("/api/v1/health").json()["version"] == APP_VERSION
