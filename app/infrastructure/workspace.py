import json
import os
from pathlib import Path
import shutil
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
    return sum(path.stat().st_size for path in root.rglob("*")
               if path.is_file() and not path.is_symlink())
