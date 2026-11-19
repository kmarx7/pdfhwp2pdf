"""macOS 앱 아이콘용 로컬 서버 시작·재사용 및 브라우저 열기."""
import argparse
import fcntl
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request

import psutil

ROOT = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:8000"
LOG_DIRECTORY = ROOT / "runtime/desktop-launcher"


def server_running() -> bool:
    result = subprocess.run(["/usr/sbin/lsof", "-nP", "-iTCP:8000", "-sTCP:LISTEN", "-t"],
                            capture_output=True, text=True, timeout=5, check=False)
    if result.returncode not in (0, 1):
        raise RuntimeError("8000번 포트의 실행 상태를 확인하지 못했습니다.")
    for value in set(result.stdout.split()):
        try:
            process = psutil.Process(int(value))
            command = process.cmdline()
            executable = Path(command[0]) if command else Path("/missing")
            if not executable.is_absolute():
                executable = ROOT / executable
            owned = (Path(process.cwd()).resolve() == ROOT
                     and "app.main:app" in command and "uvicorn" in command
                     and executable.resolve() == (ROOT / ".venv/bin/python").resolve())
            if not owned:
                raise RuntimeError("8000번 포트를 다른 프로그램이 사용하고 있습니다. 해당 프로그램을 종료하지 않았습니다.")
        except psutil.NoSuchProcess:
            return False
        except (psutil.AccessDenied, ValueError) as error:
            raise RuntimeError("서버 프로세스의 소유권을 확인하지 못했습니다.") from error
    return bool(result.stdout.strip())


def healthy() -> bool:
    # 프록시 환경 변수에 localhost 요청을 맡기지 않는다.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(URL + "/api/v1/health", timeout=1) as response:
            body = json.loads(response.read(4096))
            return body.get("status") == "ok" and body.get("api_version") == "1"
    except (OSError, ValueError, AttributeError, urllib.error.URLError):
        return False


def ensure_server(timeout=30):
    if not (ROOT / ".venv/bin/python").is_file():
        raise RuntimeError("프로젝트의 .venv Python이 없습니다. README의 설치 방법을 확인하세요.")
    LOG_DIRECTORY.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (LOG_DIRECTORY / "launcher.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        existing = server_running()
        child = None
        if not existing:
            log = LOG_DIRECTORY / "server.log"
            if log.exists() and log.stat().st_size > 5 * 1024 * 1024:
                log.replace(LOG_DIRECTORY / "server.previous.log")
            with log.open("ab") as stream:
                child = subprocess.Popen([str(ROOT / ".venv/bin/python"), str(ROOT / "scripts/run_dev.py")],
                                         cwd=ROOT, stdin=subprocess.DEVNULL, stdout=stream, stderr=stream,
                                         start_new_session=True)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if server_running() and healthy():
                return
            if child is not None and child.poll() not in (None, 0):
                raise RuntimeError("서버 시작에 실패했습니다. 프로젝트 runtime/desktop-launcher/server.log를 확인하세요.")
            time.sleep(0.25)
        raise RuntimeError("서버가 30초 안에 준비되지 않았습니다. 프로젝트 runtime/desktop-launcher/server.log를 확인하세요.")


def show_error(message):
    subprocess.run(["/usr/bin/osascript", str(ROOT / "packaging/launcher_error.applescript"), message],
                   check=False, timeout=65)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-browser", action="store_true", help="서버 준비만 확인하고 브라우저·알림을 열지 않음")
    args = parser.parse_args()
    try:
        ensure_server()
        if not args.no_browser:
            subprocess.run(["/usr/bin/open", URL], check=True, timeout=10)
        print("문서잇 준비 완료: " + URL)
        return 0
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        message = str(error) if isinstance(error, RuntimeError) else "문서잇 실행 중 오류가 발생했습니다. 프로젝트와 실행 환경을 확인하세요."
        print(message, file=sys.stderr)
        if not args.no_browser:
            show_error(message)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
