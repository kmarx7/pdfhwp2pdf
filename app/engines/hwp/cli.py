from functools import lru_cache
import hashlib
import os
import platform
from pathlib import Path
import subprocess
from typing import Callable

import psutil

from app.config import PROJECT_ROOT
from app.domain.errors import DomainError

VERSION = "1.3.1"
ARCHIVE_SHA256 = "60da60c55050aa9d72e74c0fe6bfc9b4ead9e3732cfb794cf0355ef8331926e4"
BINARY_SHA256 = "b8fe27efa4617729e22605f0e1d95f66e194c7b895e1eeadc9ad5d19300edba0"
BINARY = PROJECT_ROOT / ".tools" / "hwp-cli" / VERSION / "hwp"


@lru_cache(maxsize=4)
def verified_binary(path: str, size: int, modified: int) -> bool:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() == BINARY_SHA256


class HwpCli:
    def __init__(self, binary: Path = BINARY, emit: Callable[[dict], None] | None = None):
        self.binary = binary
        self.emit = emit or (lambda event: None)

    def available(self) -> bool:
        try:
            if (platform.system(), platform.machine()) != ("Darwin", "arm64"):
                return False
            if self.binary.is_symlink() or not os.access(self.binary, os.X_OK):
                return False
            info = self.binary.stat()
            return verified_binary(str(self.binary), info.st_size, info.st_mtime_ns)
        except OSError:
            return False

    def run(self, arguments: list[str], workspace: Path) -> None:
        if not self.available():
            raise DomainError("ENGINE_UNAVAILABLE", "HWP 변환 엔진이 설치되지 않았거나 무결성 검사에 실패했습니다.", 503,
                              suggestion="README의 HWP 엔진 설치 안내를 확인하세요.")
        try:
            with subprocess.Popen([str(self.binary), *arguments], cwd=workspace,
                                  stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  shell=False, env=os.environ | {"HWP_LANG": "en"}) as process:
                try:
                    created_at = psutil.Process(process.pid).create_time()
                    self.emit({"stage": "native_started", "pid": process.pid, "created_at": created_at})
                except psutil.NoSuchProcess:
                    pass
                try:
                    process.communicate(timeout=60)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()
                    raise
                finally:
                    self.emit({"stage": "native_finished", "pid": process.pid})
                returncode = process.returncode
        except subprocess.TimeoutExpired as exc:
            raise DomainError("CONVERSION_TIMEOUT", "HWP 변환 엔진의 처리 시간이 초과되었습니다.") from exc
        except OSError as exc:
            raise DomainError("ENGINE_UNAVAILABLE", "HWP 변환 엔진을 실행하지 못했습니다.", 503) from exc
        if returncode != 0:
            # CLI 메시지에는 문서 내용·경로가 포함될 수 있어 그대로 반환하지 않는다.
            raise DomainError("ENGINE_FAILED", "HWP 문서 구조를 해석하거나 변환하지 못했습니다.",
                              suggestion="지원하지 않는 HWP 요소가 포함되었을 수 있습니다. 원본 작성 도구에서 문서를 확인하세요.")
