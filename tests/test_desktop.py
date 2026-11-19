from pathlib import Path
import subprocess

import pytest

from app.domain.errors import DomainError
from app.services import desktop


def test_open_downloads_api_requires_csrf_same_origin_and_no_options(client, monkeypatch):
    calls = []
    monkeypatch.setattr("app.main.open_downloads_folder", lambda: calls.append(True))
    route = "/api/v1/desktop/open-downloads"
    token = client.headers.pop("X-CSRF-Token")
    assert client.post(route).status_code == 403
    client.headers["X-CSRF-Token"] = token
    assert client.post(route, headers={"Origin": "https://external.invalid"}).status_code == 403
    assert client.post(route, json={"path": "/tmp/elsewhere"}).status_code == 400
    assert not calls
    response = client.post(route)
    assert response.json() == {"status": "opened", "folder": "downloads"}
    assert calls == [True]


def test_open_downloads_uses_only_fixed_directory_without_shell(tmp_path, monkeypatch):
    folder = tmp_path / "Downloads"
    folder.mkdir()
    monkeypatch.setattr(desktop, "can_open_downloads", lambda: True)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    calls = []
    monkeypatch.setattr(desktop.subprocess, "run", lambda args, **kwargs: calls.append((args, kwargs)))
    desktop.open_downloads_folder()
    assert calls[0][0] == ["/usr/bin/open", str(folder)]
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["timeout"] == 5


@pytest.mark.parametrize("failure", ["unsupported", "missing", "timeout", "exit"])
def test_open_downloads_reports_failure(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(desktop, "can_open_downloads", lambda: failure != "unsupported")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    if failure != "missing":
        (tmp_path / "Downloads").mkdir()

    def fail(*args, **kwargs):
        if failure == "timeout":
            raise subprocess.TimeoutExpired("open", 5)
        raise subprocess.CalledProcessError(1, "open")

    monkeypatch.setattr(desktop.subprocess, "run", fail)
    with pytest.raises(DomainError) as error:
        desktop.open_downloads_folder()
    assert error.value.code == {"unsupported": "DESKTOP_UNAVAILABLE", "missing": "DOWNLOADS_FOLDER_MISSING"}.get(failure, "FOLDER_OPEN_FAILED")
