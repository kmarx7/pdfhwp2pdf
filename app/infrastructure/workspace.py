import json
import os
from pathlib import Path
import shutil
import stat
from uuid import UUID


def atomic_json(path: Path, data: dict) -> None:
    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


class JobWorkspace:
    def __init__(self, root: Path, job_id: str):
        self.root = root.resolve()
        self.path = self.root / str(UUID(job_id))
        self.check()

    def check(self) -> None:
        if self.path.is_symlink() or not self.path.resolve().is_relative_to(self.root):
            raise ValueError("Unsafe workspace")
        if self.path.exists():
            for path in self.path.rglob("*"):
                if path.is_symlink():
                    raise ValueError("Symlinks are not allowed in job workspace")

    def create(self) -> None:
        self.path.mkdir(mode=0o700)
        for name in ("input", "work", "output"):
            (self.path / name).mkdir(mode=0o700)

    def remove(self, name: str) -> None:
        self.check()
        if name not in {"input", "work", "output"}:
            raise ValueError("Unknown workspace member")
        target = self.path / name
        if target.exists():
            shutil.rmtree(target)

    def discard(self) -> None:
        self.check()
        if self.path.exists():
            shutil.rmtree(self.path)


def directory_bytes(root: Path) -> int:
    """일반 파일 크기 합. 감시 중 worker가 지우거나 옮긴 파일·폴더는 건너뛴다.

    작업 실행 중 50ms마다 호출되므로 목록 확인과 크기 조회 사이에 파일이 사라질 수 있다.
    이 경합을 오류로 올리면 정상 작업이 INTERNAL_ERROR로 실패한다.
    """
    total = 0
    # os.walk는 사라진 폴더의 scandir 오류를 기본적으로 무시하고 심볼릭 링크 폴더를 따라가지 않는다.
    for directory, _folders, files in os.walk(root, followlinks=False):
        for name in files:
            try:
                info = os.lstat(os.path.join(directory, name))
            except FileNotFoundError:
                continue
            if stat.S_ISREG(info.st_mode):
                total += info.st_size
    return total
