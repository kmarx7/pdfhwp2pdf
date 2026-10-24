import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import secrets
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.datastructures import UploadFile

from app.api.security import LocalSecurityMiddleware, check_csrf
from app.config import Settings
from app.domain.errors import DomainError
from app.engines.pdf.pdf2docx_engine import Pdf2DocxEngine
from app.engines.hwp.hwp_cli_engine import HwpCliEngine
from app.services.job_service import JobService

FRONTEND = Path(__file__).parent / "frontend"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class LeasedDownloadResponse(StreamingResponse):
    """연결 중단·전송 지연 시에도 다운로드 lease와 열린 파일을 회수한다."""

    def __init__(self, stream, key: str, service: JobService):
        async def chunks():
            while data := await asyncio.to_thread(stream.read, 64 * 1024):
                yield data

        self.stream = stream
        self.key = key
        self.service = service
        super().__init__(chunks(), media_type=DOCX_MIME,
                         headers={"Content-Disposition": 'attachment; filename="converted.docx"',
                                  "Content-Length": str(stream.seek(0, 2))})
        stream.seek(0)

    async def __call__(self, scope, receive, send):
        try:
            async with asyncio.timeout(60):
                await super().__call__(scope, receive, send)
        finally:
            self.stream.close()
            self.service.leases[self.key] -= 1
            await self.service.cleanup()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    service = JobService(settings)

    @asynccontextmanager
    async def lifespan(app):
        await service.start()
        try:
            yield
        finally:
            await service.close()

    app = FastAPI(title="문서잇 PDF·HWP → Word", version="0.3.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None)
    app.state.jobs = service
    app.state.settings = settings
    app.add_middleware(LocalSecurityMiddleware, settings=settings)

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        headers = {"Retry-After": "5"} if exc.code == "QUEUE_FULL" else {}
        return JSONResponse({"error": exc.as_dict(), "request_id": str(uuid4())}, exc.status, headers=headers)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        if exc.status_code == 413:
            error = DomainError("FILE_TOO_LARGE", "업로드 크기 제한을 초과했습니다.", 413)
        else:
            error = DomainError("INVALID_REQUEST", "요청 형식 또는 주소를 확인하세요.", exc.status_code)
        return await domain_error(request, error)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return await domain_error(request, DomainError("INVALID_REQUEST", "작업 주소 또는 요청 형식이 올바르지 않습니다."))

    @app.exception_handler(Exception)
    async def internal_error(request, exc):
        return await domain_error(request, DomainError("INTERNAL_ERROR", "서버 처리 중 오류가 발생했습니다.", 500))

    @app.get("/")
    async def index():
        return FileResponse(FRONTEND / "index.html", media_type="text/html")

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok", "api_version": "1", "version": "0.3.0"}

    @app.get("/api/v1/session")
    async def session(request: Request):
        token = request.cookies.get("pdfdocx_session") or secrets.token_urlsafe(32)
        response = JSONResponse({"csrf_token": token})
        response.set_cookie("pdfdocx_session", token, httponly=True, samesite="strict", path="/")
        return response

    @app.get("/api/v1/capabilities")
    async def capabilities():
        return {"formats": {"pdf": Pdf2DocxEngine().probe() | {"ocr": False},
                            "hwp": HwpCliEngine().probe() | {"ocr": False}},
                "limits": {"max_upload_bytes": settings.max_upload_bytes,
                           "max_pages": settings.max_pages, "ttl_seconds": settings.ttl_seconds}}

    @app.post("/api/v1/jobs", status_code=202)
    async def create_job(request: Request):
        check_csrf(request)
        # 업로드 임시 spool도 요청 종료/거부 시 context manager로 닫는다.
        async with request.form(max_files=1, max_fields=2, max_part_size=1024) as form:
            files = form.getlist("file")
            if len(files) != 1 or not isinstance(files[0], UploadFile):
                raise DomainError("INVALID_REQUEST", "PDF 또는 HWP 파일을 한 개 선택하세요.")
            if set(form.keys()) - {"file", "mode", "ocr"} or len(form.getlist("mode")) > 1 or len(form.getlist("ocr")) > 1:
                raise DomainError("INVALID_OPTIONS", "지원하지 않는 요청 필드입니다.")
            result = await service.create(files[0], str(form.get("mode", "balanced")), str(form.get("ocr", "off")))
            return JSONResponse(result, 202, headers={"Location": result["links"]["self"]})

    @app.get("/api/v1/jobs/{job_id}")
    async def get_job(job_id: UUID):
        return service.public(service.get(str(job_id)))

    @app.delete("/api/v1/jobs/{job_id}")
    async def delete_job(job_id: UUID, request: Request):
        check_csrf(request)
        changed = await service.delete(str(job_id))
        return Response(status_code=202 if changed else 204)

    @app.get("/api/v1/jobs/{job_id}/quality")
    async def quality(job_id: UUID):
        job = service.get(str(job_id))
        if job["state"] != "succeeded":
            raise DomainError("RESULT_NOT_READY", "아직 품질 보고서가 준비되지 않았습니다.", 409)
        return json.loads((service.space(str(job_id)).path / "output/quality.json").read_text())

    @app.get("/api/v1/jobs/{job_id}/download")
    async def download(job_id: UUID):
        key = str(job_id)
        job = service.get(key)
        if job["state"] != "succeeded":
            raise DomainError("RESULT_NOT_READY", "다운로드할 수 있는 변환 결과가 없습니다.", 409)
        path = service.space(key).path / "output/result.docx"
        try:
            stream = path.open("rb")
        except OSError as exc:
            raise DomainError("RESULT_MISSING", "결과 파일을 찾지 못했습니다.", 410) from exc
        service.leases[key] = service.leases.get(key, 0) + 1
        return LeasedDownloadResponse(stream, key, service)

    app.mount("/static", StaticFiles(directory=FRONTEND / "static"), name="static")
    return app


app = create_app()
