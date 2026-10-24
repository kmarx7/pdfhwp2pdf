"""로컬 단일 서버 실행. --restart는 이 프로젝트의 8000번 서버만 재시작한다."""
import argparse
from pathlib import Path
import subprocess
import sys

import psutil

ROOT = Path(__file__).resolve().parents[1]
COMMAND = [str(ROOT / ".venv/bin/python"), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
           "--port", "8000", "--workers", "1", "--no-access-log"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restart", action="store_true")
    options = parser.parse_args()
    result = subprocess.run(["lsof", "-nP", "-iTCP:8000", "-sTCP:LISTEN", "-t"],
                            capture_output=True, text=True, check=False)
    if result.returncode not in (0, 1):
        raise SystemExit("8000번 포트의 서버 상태를 확인하지 못했습니다.")
    for value in set(result.stdout.split()):
        process = psutil.Process(int(value))
        command = process.cmdline()
        executable = Path(command[0]) if command else Path("/missing")
        if not executable.is_absolute():
            executable = ROOT / executable
        owned = (Path(process.cwd()).resolve() == ROOT
                 and "app.main:app" in command and "uvicorn" in command
                 and executable.resolve() == (ROOT / ".venv/bin/python").resolve())
        if not owned:
            raise SystemExit("8000번 포트를 다른 프로그램이 사용 중입니다. 해당 프로그램을 종료하지 않았습니다.")
        if not options.restart:
            print("문서잇 서버가 이미 실행 중입니다: http://127.0.0.1:8000")
            return 0
        print("이 프로젝트의 로컬 서버를 재시작합니다.", flush=True)
        process.terminate()
        try:
            process.wait(timeout=10)
        except psutil.TimeoutExpired:
            raise SystemExit("기존 서버가 종료되지 않아 재시작을 중단했습니다.")
        except psutil.NoSuchProcess:
            pass
    try:
        return subprocess.call(COMMAND, cwd=ROOT)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
