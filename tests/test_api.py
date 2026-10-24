import asyncio
from dataclasses import replace
from io import BytesIO
import json
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from starlette.datastructures import UploadFile

from app.config import Settings
from app.domain.errors import DomainError
from app.main import create_app
from app.services.job_service import JobService
from tests.conftest import submit, wait_job


def test_home_health_capabilities_and_security_headers(client):
    assert 'lang="ko"' in client.get("/").text
    assert client.get("/api/v1/health").json()["status"] == "ok"
    assert client.get("/static/app.js").status_code == 200
    capability = client.get("/api/v1/capabilities").json()
    assert capability["formats"]["pdf"]["availability"] == "experimental"
    assert capability["formats"]["pdf"]["modes"] == ["balanced"]
    assert capability["formats"]["pdf"]["ocr"] is False
    assert client.get("/").headers["content-security-policy"].startswith("default-src 'self'")


def test_csrf_and_foreign_origin_rejected(client, samples):
    token = client.headers.pop("X-CSRF-Token")
    assert submit(client, samples["text"]).status_code == 403
    client.headers["X-CSRF-Token"] = token
    client.headers["Origin"] = "https://external.invalid"
    assert submit(client, samples["text"]).status_code == 403
    assert client.get("/", headers={"Host": "external.invalid"}).status_code == 400


@pytest.mark.parametrize(("filename", "content", "status"), [
    ("wrong.txt", b"%PDF-1.7", 415), ("wrong.pdf", b"hello", 400), ("empty.pdf", b"", 400),
])
def test_upload_rejections_leave_no_workspace(client, filename, content, status):
    response = client.post("/api/v1/jobs", files={"file": (filename, content, "application/pdf")})
    assert response.status_code == status
    assert not client.app.state.jobs.jobs
    assert not any(path.is_dir() for path in client.app.state.jobs.root.iterdir())


def test_options_multipart_and_job_id_validation(client, samples):
    assert submit(client, samples["text"], mode="layout").status_code == 422
    assert submit(client, samples["text"], ocr="auto").status_code == 422
    assert client.post("/api/v1/jobs", data={"mode": "balanced"}).status_code == 422
    assert client.get("/api/v1/jobs/not-a-uuid").status_code == 422
    assert client.get(f"/api/v1/jobs/{uuid4()}").status_code == 404
    assert client.post("/api/v1/jobs", files=[("file", ("a.pdf", b"%PDF-1.7")), ("file", ("b.pdf", b"%PDF-1.7"))]).status_code == 400


def test_size_limit_before_and_after_multipart(tmp_path, samples):
    settings = replace(Settings(), workspace=tmp_path / "small", max_upload_bytes=100, allowed_hosts=("testserver",))
    with TestClient(create_app(settings)) as client:
        client.headers["X-CSRF-Token"] = client.get("/api/v1/session").json()["csrf_token"]
        assert submit(client, samples["text"]).status_code == 413
        assert client.post("/api/v1/jobs", content=b"X" * 66000).status_code == 413
        assert not client.app.state.jobs.jobs


def test_chunked_request_limit_before_multipart_spooling(tmp_path):
    settings = replace(Settings(), workspace=tmp_path / "chunked", max_upload_bytes=100, allowed_hosts=("testserver",))
    with TestClient(create_app(settings)) as client:
        client.headers["X-CSRF-Token"] = client.get("/api/v1/session").json()["csrf_token"]

        def chunks():
            yield b'--test-boundary\r\nContent-Disposition: form-data; name="file"; filename="large.pdf"\r\nContent-Type: application/pdf\r\n\r\n'
            yield b"%PDF-1.7\n" + b"X" * 70000
            yield b"\r\n--test-boundary--\r\n"

        response = client.post("/api/v1/jobs", content=chunks(), headers={"Content-Type": "multipart/form-data; boundary=test-boundary"})
        assert response.status_code == 413
        assert not client.app.state.jobs.jobs


def test_result_delete_and_tombstone(client, samples):
    job = wait_job(client, submit(client, samples["text"]).json()["job_id"])
    url = job["links"]["self"]
    assert client.delete(url).status_code == 202
    assert client.get(url).status_code == 410
    assert client.get(url + "/download").status_code == 410
    assert client.delete(url).status_code == 204
    space = client.app.state.jobs.space(job["job_id"]).path
    assert list(path.name for path in space.iterdir()) == ["meta.json"]
    meta = json.loads((space / "meta.json").read_text())
    assert "output_sha256" not in meta and "warnings" not in meta


def test_active_cancel_cleans_files(client, samples):
    response = submit(client, samples["multipage"])
    key = response.json()["job_id"]
    assert client.delete(f"/api/v1/jobs/{key}").status_code == 202
    import time
    for _ in range(100):
        job = client.app.state.jobs.jobs[key]
        if job["state"] == "expired":
            break
        time.sleep(0.05)
    assert client.app.state.jobs.jobs[key]["state"] == "expired"
    assert not (client.app.state.jobs.space(key).path / "input").exists()


def test_expiry_lease_and_tombstone_removal(tmp_path, samples):
    async def scenario():
        now = [1000.0]
        settings = replace(Settings(), workspace=tmp_path / "expiry", ttl_seconds=10, tombstone_seconds=20)
        service = JobService(settings, clock=lambda: now[0])
        service.root.mkdir()
        job = await service.create(UploadFile(BytesIO(samples["text"].read_bytes()), filename="test.pdf"), "balanced", "off")
        key = job["job_id"]
        service.finish(service.jobs[key], "succeeded")
        now[0] += 11
        with pytest.raises(DomainError) as caught:
            service.get(key)
        assert caught.value.status == 410
        service.leases[key] = 1
        await service.cleanup()
        assert service.jobs[key]["state"] == "succeeded"
        service.leases[key] = 0
        await service.cleanup()
        assert service.jobs[key]["state"] == "expired"
        now[0] += 21
        await service.cleanup()
        assert key not in service.jobs
    asyncio.run(scenario())


def test_bounded_queue_rejects_extra_upload(tmp_path, samples):
    async def scenario():
        service = JobService(replace(Settings(), workspace=tmp_path / "queue", queue_size=1))
        service.root.mkdir()
        await service.create(UploadFile(BytesIO(samples["text"].read_bytes()), filename="test.pdf"), "balanced", "off")
        with pytest.raises(DomainError) as caught:
            await service.create(UploadFile(BytesIO(samples["text"].read_bytes()), filename="test.pdf"), "balanced", "off")
        assert caught.value.code == "QUEUE_FULL"
        assert len(service.jobs) == 1
    asyncio.run(scenario())


def test_download_disconnect_releases_lease_and_file(tmp_path):
    from app.main import LeasedDownloadResponse
    from starlette.requests import ClientDisconnect

    async def scenario():
        service = JobService(replace(Settings(), workspace=tmp_path / "disconnect"))
        service.root.mkdir()
        service.leases["test"] = 1
        stream = BytesIO(b"file bytes")
        response = LeasedDownloadResponse(stream, "test", service)

        async def send(message):
            if message["type"] == "http.response.body":
                raise OSError("client disconnected")

        async def receive():
            return {"type": "http.disconnect"}

        with pytest.raises(ClientDisconnect):
            await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)
        assert stream.closed
        assert service.leases["test"] == 0

    asyncio.run(scenario())
