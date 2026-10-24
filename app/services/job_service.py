import asyncio
from contextlib import suppress
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time
from uuid import uuid4

import psutil

from app.config import PROJECT_ROOT, Settings
from app.domain.errors import DomainError
from app.infrastructure.workspace import JobWorkspace, atomic_json, directory_bytes

TERMINAL = {"succeeded", "failed", "cancelled", "expired"}
STAGES = {"analyzing", "converting", "postprocessing", "validating"}


def timestamp(value: float | None) -> str | None:
    return datetime.fromtimestamp(value, timezone.utc).isoformat() if value is not None else None


class JobService:
    def __init__(self, settings: Settings, clock=time.time):
        self.settings = settings
        self.clock = clock
        self.root = settings.workspace
        self.jobs: dict[str, dict] = {}
        self.leases: dict[str, int] = {}
        self.queue: asyncio.Queue[str] = asyncio.Queue(settings.queue_size)
        self.active: asyncio.subprocess.Process | None = None
        self.tasks = []
        self.closed = False
        self.lock_file = None

    async def start(self) -> None:
        if self.root.is_symlink():
            raise RuntimeError("Workspace cannot be a symlink")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root = self.root.resolve()
        self.lock_file = (self.root / ".server.lock").open("a+")
        try:
            fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock_file.close()
            raise RuntimeError("작업 저장소를 이미 사용 중입니다. 단일 서버 worker로 실행하세요.")
        for path in self.root.iterdir():
            if not path.is_dir() or path.is_symlink():
                continue
            try:
                space = JobWorkspace(self.root, path.name)
            except ValueError:
                continue
            try:
                job = json.loads((path / "meta.json").read_text())
                if job["job_id"] != path.name:
                    raise ValueError("mismatch")
            except (OSError, ValueError, KeyError):
                space.discard()
                continue
            self.jobs[path.name] = job
            if job["state"] not in TERMINAL:
                await self.reap_previous_worker(job)
                self.finish(job, "failed", DomainError("INTERRUPTED", "서버가 종료되어 작업이 중단되었습니다."))
            elif job["state"] == "succeeded":
                output = path / "output/result.docx"
                if not output.is_file() or hashlib.sha256(output.read_bytes()).hexdigest() != job.get("output_sha256"):
                    self.finish(job, "failed", DomainError("VALIDATION_FAILED", "보관된 결과의 무결성 확인에 실패했습니다."))
            self.clean_intermediates(job)
        await self.cleanup()
        self.tasks = [asyncio.create_task(self.work_loop()), asyncio.create_task(self.cleanup_loop())]

    async def reap_previous_worker(self, job: dict) -> None:
        """PID 재사용을 막기 위해 생성 시각·실행 인자까지 일치하는 소유 자식만 회수한다."""
        pid = job.get("worker_pid")
        if not pid:
            return
        try:
            process = psutil.Process(pid)
            command = process.cmdline()
            expected_path = str(self.space(job["job_id"]).path)
            if (process.create_time() != job.get("worker_created_at")
                    or "app.infrastructure.worker" not in command or expected_path not in command):
                return
            if os.getpgid(pid) != pid:
                return
            with suppress(ProcessLookupError):
                os.killpg(pid, signal.SIGTERM)
            try:
                await asyncio.to_thread(process.wait, 5)
            except psutil.TimeoutExpired:
                with suppress(ProcessLookupError):
                    os.killpg(pid, signal.SIGKILL)
                await asyncio.to_thread(process.wait, 5)
        except psutil.NoSuchProcess:
            return

    async def close(self) -> None:
        self.closed = True
        for task in self.tasks:
            task.cancel()
        if self.active:
            await self.stop_process(self.active)
        await asyncio.gather(*self.tasks, return_exceptions=True)
        for job in self.jobs.values():
            if job["state"] not in TERMINAL:
                self.finish(job, "failed", DomainError("INTERRUPTED", "서버가 종료되어 작업이 중단되었습니다."))
                self.clean_intermediates(job)
        if self.lock_file and not self.lock_file.closed:
            fcntl.flock(self.lock_file, fcntl.LOCK_UN)
            self.lock_file.close()

    def space(self, job_id: str) -> JobWorkspace:
        return JobWorkspace(self.root, job_id)

    def persist(self, job: dict) -> None:
        space = self.space(job["job_id"])
        atomic_json(space.path / "meta.json", job)

    def finish(self, job: dict, state: str, error: DomainError | None = None) -> None:
        job.update(state=state, stage=state, finished_at=self.clock(),
                   expires_at=self.clock() + self.settings.ttl_seconds,
                   error=error.as_dict() if error else None)
        self.persist(job)

    def clean_intermediates(self, job: dict) -> None:
        try:
            space = self.space(job["job_id"])
            space.remove("input")
            space.remove("work")
            if job["state"] != "succeeded":
                space.remove("output")
            job.pop("cleanup_error", None)
        except (OSError, ValueError):
            job["cleanup_error"] = "CLEANUP_FAILED"
        self.persist(job)

    async def create(self, upload, mode: str, ocr: str) -> dict:
        if mode != "balanced" or ocr != "off":
            raise DomainError("INVALID_OPTIONS", "현재 균형 모드만 지원하며 OCR은 제공하지 않습니다.")
        # 사용자 파일명은 디스크 경로·다운로드 헤더·메타데이터로 사용하지 않는다.
        if not (upload.filename or "").lower().endswith(".pdf"):
            raise DomainError("UNSUPPORTED_FORMAT", "현재 PDF 파일만 변환할 수 있습니다.", 415)
        if self.queue.full():
            raise DomainError("QUEUE_FULL", "변환 대기열이 가득 찼습니다.", 429)
        if directory_bytes(self.root) >= self.settings.max_workspace_bytes:
            raise DomainError("RESOURCE_LIMIT", "임시 저장 공간이 부족합니다.", 503)
        job_id = str(uuid4())
        space = self.space(job_id)
        space.create()
        committed = False
        try:
            size = 0
            target = space.path / "input/source.pdf"
            with target.open("wb") as stream:
                while chunk := await upload.read(64 * 1024):
                    size += len(chunk)
                    if size > self.settings.max_upload_bytes:
                        raise DomainError("FILE_TOO_LARGE", "PDF 파일은 30 MiB까지 업로드할 수 있습니다.", 413)
                    stream.write(chunk)
            if not size:
                raise DomainError("INVALID_DOCUMENT", "비어 있는 파일입니다.", 400)
            with target.open("rb") as stream:
                if not stream.read(8).startswith(b"%PDF-"):
                    raise DomainError("INVALID_DOCUMENT", "PDF 형식의 파일이 아닙니다.", 400)
            target.chmod(0o400)
            if self.queue.full():
                raise DomainError("QUEUE_FULL", "변환 대기열이 가득 찼습니다.", 429)
            if directory_bytes(self.root) > self.settings.max_workspace_bytes:
                raise DomainError("RESOURCE_LIMIT", "임시 저장 공간이 부족합니다.", 503)
            job = {"job_id": job_id, "state": "queued", "stage": "waiting", "format": "pdf",
                   "mode": mode, "size_bytes": size, "pages": None, "engine": None,
                   "warnings": [], "error": None, "created_at": self.clock(), "expires_at": None}
            self.jobs[job_id] = job
            self.persist(job)
            self.queue.put_nowait(job_id)
            committed = True
            return self.public(job)
        finally:
            await upload.close()
            if not committed:
                self.jobs.pop(job_id, None)
                space.discard()

    def get(self, job_id: str) -> dict:
        job = self.jobs.get(job_id)
        if job is None:
            raise DomainError("JOB_NOT_FOUND", "작업을 찾을 수 없습니다.", 404)
        if job.get("deleted_at") is not None or (job.get("expires_at") is not None and job["expires_at"] <= self.clock()):
            raise DomainError("JOB_EXPIRED", "삭제되었거나 보관 기간이 만료된 작업입니다.", 410)
        return job

    def public(self, job: dict) -> dict:
        url = f'/api/v1/jobs/{job["job_id"]}'
        return {key: job[key] for key in ("job_id", "state", "stage", "format", "mode", "size_bytes", "engine", "warnings", "error")} | {
            "progress": {"fraction": None, "completed_pages": job["pages"] if job["state"] == "succeeded" else None,
                         "total_pages": job["pages"]},
            "created_at": timestamp(job["created_at"]), "expires_at": timestamp(job.get("expires_at")),
            "links": {"self": url, "download": url + "/download" if job["state"] == "succeeded" else None,
                      "quality": url + "/quality" if job["state"] == "succeeded" else None},
        }

    async def delete(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if not job:
            raise DomainError("JOB_NOT_FOUND", "작업을 찾을 수 없습니다.", 404)
        if job.get("deleted_at") is not None:
            return False
        job["deleted_at"] = self.clock()
        if job["state"] not in TERMINAL:
            job.update(state="cancelling", stage="cancelling")
        self.persist(job)
        await self.cleanup()
        return True

    async def cleanup(self) -> None:
        now = self.clock()
        for job_id, job in list(self.jobs.items()):
            due = job.get("deleted_at") is not None or (job.get("expires_at") is not None and job["expires_at"] <= now)
            if job["state"] not in TERMINAL:
                continue
            if not due:
                if job.get("cleanup_error"):
                    self.clean_intermediates(job)
                continue
            if self.leases.get(job_id, 0):
                continue
            try:
                space = self.space(job_id)
                for member in ("input", "work", "output"):
                    space.remove(member)
                if job.get("deleted_at") is None:
                    job["deleted_at"] = now
                # tombstone에 문서 정보·hash·오류 상세를 남기지 않는다.
                tombstone = {"job_id": job_id, "state": "expired", "stage": "expired",
                             "deleted_at": job["deleted_at"], "expires_at": job["deleted_at"],
                             "created_at": job["created_at"]}
                self.jobs[job_id] = tombstone
                self.persist(tombstone)
                if now - tombstone["deleted_at"] >= self.settings.tombstone_seconds:
                    space.discard()
                    del self.jobs[job_id]
            except (OSError, ValueError):
                job["cleanup_error"] = "CLEANUP_FAILED"

    async def cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.cleanup_interval)
            await self.cleanup()

    async def stop_process(self, process) -> None:
        if process.returncode is not None:
            return
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGTERM)
        try:
            await asyncio.wait_for(process.wait(), 5)
        except asyncio.TimeoutError:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            await process.wait()

    async def execute(self, job: dict) -> None:
        space = self.space(job["job_id"])
        result = None
        failure = None
        start = time.monotonic()
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "app.infrastructure.worker", str(space.path), str(self.settings.max_pages), str(os.getpid()),
            cwd=PROJECT_ROOT, start_new_session=True, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        self.active = process
        try:
            job["worker_pid"] = process.pid
            job["worker_created_at"] = psutil.Process(process.pid).create_time()
            self.persist(job)
        except psutil.NoSuchProcess:
            pass

        async def events():
            nonlocal result, failure
            async for line in process.stdout:
                event = json.loads(line)
                stage = event.get("stage")
                if stage in STAGES and job["state"] != "cancelling":
                    job.update(state=stage, stage=stage)
                    if "pages" in event:
                        job["pages"] = event["pages"]
                        job["warnings"] = event.get("warnings", [])
                    self.persist(job)
                elif stage == "complete":
                    result = event
                elif stage == "failed":
                    failure = event["error"]

        reader = asyncio.create_task(events())
        peak_memory = 0
        try:
            while process.returncode is None:
                if job.get("deleted_at") is not None:
                    await self.stop_process(process)
                    break
                if time.monotonic() - start >= self.settings.timeout_seconds:
                    raise DomainError("CONVERSION_TIMEOUT", "변환 제한 시간(180초)을 초과했습니다.")
                try:
                    memory = psutil.Process(process.pid).memory_info().rss
                    peak_memory = max(peak_memory, memory)
                    if memory > self.settings.max_memory_bytes or directory_bytes(self.root) > self.settings.max_workspace_bytes:
                        raise DomainError("RESOURCE_LIMIT", "변환 작업이 메모리 또는 저장 공간 제한을 초과했습니다.")
                except psutil.NoSuchProcess:
                    pass
                await asyncio.sleep(0.05)
            await process.wait()
            await reader
            if job.get("deleted_at") is not None:
                self.finish(job, "cancelled")
            elif failure:
                self.finish(job, "failed", DomainError(failure["code"], failure["message"],
                            details=failure.get("details"), suggestion=failure.get("suggestion", "다른 파일로 시도하세요.")))
            elif process.returncode != 0 or not result:
                self.finish(job, "failed", DomainError("ENGINE_FAILED", "변환 프로세스가 정상적으로 완료되지 않았습니다."))
            else:
                output = space.path / "output/result.docx"
                if not output.is_file() or hashlib.sha256(output.read_bytes()).hexdigest() != result["sha256"]:
                    raise DomainError("VALIDATION_FAILED", "결과 파일의 무결성 확인에 실패했습니다.")
                job.update(engine=result["engine"], pages=result["pages"], output_sha256=result["sha256"])
                self.finish(job, "succeeded")
        finally:
            await self.stop_process(process)
            reader.cancel()
            await asyncio.gather(reader, return_exceptions=True)
            self.active = None
            job["elapsed_seconds"] = round(time.monotonic() - start, 3)
            job["peak_rss_bytes"] = peak_memory

    async def work_loop(self) -> None:
        while True:
            job_id = await self.queue.get()
            job = self.jobs.get(job_id)
            try:
                if not job:
                    continue
                if job.get("deleted_at") is not None:
                    self.finish(job, "cancelled")
                else:
                    await self.execute(job)
            except DomainError as exc:
                self.finish(job, "failed", exc)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.finish(job, "failed", DomainError("INTERNAL_ERROR", "작업 처리 중 오류가 발생했습니다.", 500))
            finally:
                if job and job["state"] in TERMINAL:
                    self.clean_intermediates(job)
                self.queue.task_done()
                await self.cleanup()
