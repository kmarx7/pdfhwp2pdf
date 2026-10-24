import secrets
from urllib.parse import urlsplit

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse


class LocalSecurityMiddleware:
    """요청 본문을 multipart 파서보다 먼저 제한하고 로컬 요청을 검사한다."""

    def __init__(self, app, settings):
        self.app = app
        self.settings = settings

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        host = headers.get(b"host", b"").decode("latin1")
        hostname = urlsplit("http://" + host).hostname or ""
        allowed = {item.strip("[]") for item in self.settings.allowed_hosts}
        if hostname not in allowed:
            response = JSONResponse({"error": {"code": "INVALID_HOST", "message": "허용되지 않은 서버 주소입니다."}}, 400)
            return await response(scope, receive, send)
        if scope["method"] in {"POST", "DELETE", "PUT", "PATCH"}:
            origin = headers.get(b"origin", b"").decode("latin1")
            expected = scope.get("scheme", "http") + "://" + host
            if origin and origin != expected:
                response = JSONResponse({"error": {"code": "INVALID_ORIGIN", "message": "같은 웹페이지에서 요청하세요."}}, 403)
                return await response(scope, receive, send)
        limit = self.settings.max_upload_bytes * (2 if scope["path"] == "/api/v1/native/jobs" else 1) + 64 * 1024
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            declared = limit + 1
        if declared > limit or declared < 0:
            response = JSONResponse({"error": {"code": "FILE_TOO_LARGE", "message": "업로드 크기 제한을 초과했습니다."}}, 413)
            return await response(scope, receive, send)
        received = 0

        async def bounded_receive():
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > limit:
                raise HTTPException(413, detail="FILE_TOO_LARGE")
            return message

        async def secure_send(message):
            if message["type"] == "http.response.start":
                extra = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"cache-control", b"no-store"),
                    (b"content-security-policy", b"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"),
                ]
                message["headers"] = [pair for pair in message.get("headers", []) if pair[0].lower() not in {x[0] for x in extra}] + extra
            await send(message)

        await self.app(scope, bounded_receive, secure_send)


def check_csrf(request):
    cookie = request.cookies.get("pdfdocx_session", "")
    token = request.headers.get("x-csrf-token", "")
    if not cookie or not secrets.compare_digest(cookie, token):
        from app.domain.errors import DomainError
        raise DomainError("CSRF_FAILED", "페이지를 새로고침한 뒤 다시 시도하세요.", 403)
