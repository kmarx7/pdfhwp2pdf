"""로컬 macOS의 고정된 다운로드 폴더만 연다. 요청에서 경로를 받지 않는다."""
from pathlib import Path
import subprocess
import sys

from app.domain.errors import DomainError


def can_open_downloads() -> bool:
    return sys.platform == "darwin" and Path("/usr/bin/open").is_file()


def open_downloads_folder() -> None:
    if not can_open_downloads():
        raise DomainError("DESKTOP_UNAVAILABLE", "다운로드 폴더 열기는 로컬 macOS에서 지원합니다.", 409)
    folder = Path.home() / "Downloads"
    if not folder.is_dir():
        raise DomainError("DOWNLOADS_FOLDER_MISSING", "기본 다운로드 폴더를 찾을 수 없습니다.", 404,
                          suggestion="브라우저의 다운로드 목록에서 저장 위치를 확인하세요.")
    try:
        subprocess.run(["/usr/bin/open", str(folder)], shell=False, check=True, timeout=5,
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        raise DomainError("FOLDER_OPEN_FAILED", "다운로드 폴더를 열지 못했습니다.", 503,
                          suggestion="Finder에서 다운로드 폴더를 열거나 브라우저의 다운로드 목록을 확인하세요.") from exc
