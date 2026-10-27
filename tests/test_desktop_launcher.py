from types import SimpleNamespace

import pytest

from scripts import launch_desktop as launcher


@pytest.fixture
def local_launcher(monkeypatch, tmp_path):
    python = tmp_path / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.touch()
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    monkeypatch.setattr(launcher, "LOG_DIRECTORY", tmp_path / "logs")
    monkeypatch.setattr(launcher.time, "sleep", lambda _: None)


def test_existing_server_is_reused_without_starting_another(local_launcher, monkeypatch):
    monkeypatch.setattr(launcher, "server_running", lambda: True)
    monkeypatch.setattr(launcher, "healthy", lambda: True)
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *a, **kw: pytest.fail("duplicate server"))
    launcher.ensure_server()


def test_new_server_is_detached_and_waits_for_health(local_launcher, monkeypatch):
    states = iter([False, False, True])
    monkeypatch.setattr(launcher, "server_running", lambda: next(states))
    monkeypatch.setattr(launcher, "healthy", lambda: True)
    starts = []
    def start(command, **options):
        starts.append((command, options))
        return SimpleNamespace(poll=lambda: None)
    monkeypatch.setattr(launcher.subprocess, "Popen", start)
    launcher.ensure_server()
    assert len(starts) == 1 and starts[0][1]["start_new_session"] is True
    assert starts[0][0][0] == str(launcher.ROOT / ".venv/bin/python")


def test_failed_start_is_not_reported_ready(local_launcher, monkeypatch):
    monkeypatch.setattr(launcher, "server_running", lambda: False)
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *a, **kw: SimpleNamespace(poll=lambda: 1))
    with pytest.raises(RuntimeError, match="서버 시작에 실패"):
        launcher.ensure_server()


def test_foreign_port_owner_is_not_terminated(local_launcher, monkeypatch):
    monkeypatch.setattr(launcher.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout="123\n"))
    monkeypatch.setattr(launcher.psutil, "Process", lambda _: SimpleNamespace(cmdline=lambda: ["/other/python", "server.py"], cwd=lambda: "/other"))
    with pytest.raises(RuntimeError, match="다른 프로그램"):
        launcher.server_running()
