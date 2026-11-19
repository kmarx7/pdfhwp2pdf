from dataclasses import replace
from pathlib import Path
from urllib.parse import quote
import unicodedata

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.main import create_app
from app.services.filenames import make_download_filename, content_disposition, job_download_filename
from tests.conftest import wait_job
from tests.test_native_web import native_client, hello_pdf


@pytest.mark.parametrize("original,expected", [
    ("사업 계획서 (최종).hwp", "사업 계획서 (최종).docx"),
    ("report.v2.final.PDF", "report.v2.final.docx"),
    ("../../private/보고서.pdf", "보고서.docx"),
    (r"C:\fakepath\보고서.hwp", "보고서.docx"),
    ('bad\r\nname<>:"?*.pdf', "badname______.docx"),
    (".pdf", "converted.docx"), (None, "converted.docx"),
    ("CON.pdf", "_CON.docx"), ("a\u202eb.pdf", "ab.docx"),
])
def test_download_name_preserves_safe_basename(original, expected):
    assert make_download_filename(original, "docx") == expected


def test_unicode_normalization_limits_and_header_safety():
    assert make_download_filename(unicodedata.normalize("NFD", "한글.pdf"), "pdf") == "한글.pdf"
    long_name = make_download_filename("가" * 300 + ".hwp", "pdf")
    assert len(long_name.encode("utf-8")) <= 240 and long_name.endswith(".pdf")
    header = content_disposition("한글 자료 (1).docx", "docx")
    assert "filename*=UTF-8''" + quote("한글 자료 (1).docx", safe="") in header
    assert "\r" not in content_disposition("x\r\ny.docx", "docx")
    assert "\n" not in content_disposition("x\r\ny.docx", "docx")
    assert job_download_filename({"output_format": "pdf"}) == "converted.pdf"
    assert job_download_filename({}) == "converted.docx"


@pytest.mark.parametrize("route,source_kind,filename,expected", [
    ("/api/v1/jobs", "pdf", "월간 보고서.v2.PDF", "월간 보고서.v2.docx"),
    ("/api/v1/jobs", "hwp", "한글 자료 (최종).hwp", "한글 자료 (최종).docx"),
    ("/api/v1/native/jobs", "pdf", "글꼴 포함 보고서.pdf", "글꼴 포함 보고서.docx"),
    ("/api/v1/native/jobs", "hwp", "원본 문서.hwp", "원본 문서.docx"),
    ("/api/v1/hwp-pdf/jobs", "hwp", "PDF로 저장할 문서.hwp", "PDF로 저장할 문서.pdf"),
])
def test_all_conversion_routes_preserve_unicode_download_filename(native_client, samples, hello_pdf, route, source_kind, filename, expected):
    source = samples["text"] if source_kind == "pdf" else Path(__file__).parent / "fixtures/hwp/hello_world.hwp"
    files = {"file": (filename, source.read_bytes())}
    if route == "/api/v1/native/jobs" and source_kind == "hwp":
        files["reference"] = ("reference.pdf", hello_pdf.read_bytes())
    response = native_client.post(route, files=files)
    assert response.status_code == 202, response.text
    assert response.json()["download_filename"] == expected
    job = wait_job(native_client, response.json()["job_id"])
    assert job["state"] == "succeeded", job
    assert job["download_filename"] == expected
    downloaded = native_client.get(job["links"]["download"])
    assert "filename*=UTF-8''" + quote(expected, safe="") in downloaded.headers["content-disposition"]
    assert downloaded.headers["content-type"] == ("application/pdf" if expected.endswith(".pdf") else "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    assert native_client.delete(job["links"]["self"]).status_code == 202
    meta = (native_client.app.state.jobs.space(job["job_id"]).path / "meta.json").read_text()
    assert "download_filename" not in meta and filename not in meta


def test_download_filename_survives_server_restart(tmp_path, samples):
    settings = replace(Settings(), workspace=tmp_path / "jobs", allowed_hosts=("testserver",))
    with TestClient(create_app(settings)) as client:
        client.headers["X-CSRF-Token"] = client.get("/api/v1/session").json()["csrf_token"]
        response = client.post("/api/v1/jobs", files={"file": ("재시작 후 보고서.pdf", samples["text"].read_bytes())})
        job = wait_job(client, response.json()["job_id"])
        assert job["state"] == "succeeded", job
    with TestClient(create_app(settings)) as client:
        restored = client.get(job["links"]["self"]).json()
        assert restored["download_filename"] == "재시작 후 보고서.docx"
        assert "filename*=UTF-8''" + quote("재시작 후 보고서.docx", safe="") in client.get(restored["links"]["download"]).headers["content-disposition"]
