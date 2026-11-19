"""작업 폴더 용량 감시와 worker의 파일 삭제·이동 경합 회귀 테스트."""
import shutil
import threading
from pathlib import Path

from app.infrastructure import workspace
from app.infrastructure.workspace import directory_bytes


def test_directory_bytes_ignores_file_removed_after_listing(tmp_path, monkeypatch):
    (tmp_path / "kept.bin").write_bytes(b"x" * 10)
    vanishing = tmp_path / "work" / "temp.docx"
    vanishing.parent.mkdir()
    vanishing.write_bytes(b"y" * 99)
    original_walk = workspace.os.walk

    def walk_then_delete(*args, **kwargs):
        for directory, folders, files in original_walk(*args, **kwargs):
            if Path(directory) == vanishing.parent:
                # 목록 확인 직후, 크기 조회 전에 worker가 임시 파일을 지운 상태를 재현한다.
                vanishing.unlink()
            yield directory, folders, files

    monkeypatch.setattr(workspace.os, "walk", walk_then_delete)
    assert directory_bytes(tmp_path) == 10


def test_directory_bytes_counts_regular_files_only(tmp_path):
    (tmp_path / "a.bin").write_bytes(b"x" * 7)
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "b.bin").write_bytes(b"y" * 5)
    (tmp_path / "link.bin").symlink_to(tmp_path / "a.bin")
    (tmp_path / "link-dir").symlink_to(tmp_path / "nested", target_is_directory=True)
    assert directory_bytes(tmp_path) == 12


def test_directory_bytes_survives_concurrent_directory_churn(tmp_path):
    root = tmp_path / "jobs"
    root.mkdir()
    stop = threading.Event()

    def churn():
        index = 0
        while not stop.is_set():
            work = root / f"job{index % 3}" / "work"
            (work / "tmp").mkdir(parents=True, exist_ok=True)
            for number in range(5):
                (work / "tmp" / f"f{number}").write_bytes(b"x" * 100)
            (work / "tmp" / "f0").replace(root / f"job{index % 3}" / "out")
            shutil.rmtree(work, ignore_errors=True)
            index += 1

    worker = threading.Thread(target=churn)
    worker.start()
    try:
        for _ in range(3000):
            assert directory_bytes(root) >= 0
    finally:
        stop.set()
        worker.join()
