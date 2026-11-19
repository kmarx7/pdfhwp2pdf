from dataclasses import replace
import hashlib
import json

from fastapi.testclient import TestClient
import pymupdf
import pytest

from app.config import Settings
from app.domain.errors import DomainError
from app.domain.models import DocumentAnalysis
from app.main import create_app
from app.quality.pdf_validator import PdfQualityValidator
from app.quality.validator import normalized
from tests.conftest import wait_job
from tests.test_hwp import hwp_samples


def submit_pdf(client, source):
    return client.post("/api/v1/hwp-pdf/jobs", files={"file": (source.name, source.read_bytes())})


@pytest.mark.parametrize("kind", ["text", "table", "merged", "image", "sections", "colored"])
def test_hwp_to_pdf_real_engine_download_and_cleanup(client, hwp_samples, kind):
    source = hwp_samples[kind]
    before = source.read_bytes()
    response = submit_pdf(client, source)
    assert response.status_code == 202, response.text
    assert response.json()["output_format"] == "pdf"
    job = wait_job(client, response.json()["job_id"])
    assert job["state"] == "succeeded", job
    assert job["engine"] == {"id": "hwp-cli-pdf", "version": "1.3.1"}
    download = client.get(job["links"]["download"])
    assert download.headers["content-type"] == "application/pdf"
    assert download.headers["content-disposition"] == f'attachment; filename="{source.stem}.pdf"'
    with pymupdf.open(stream=download.content, filetype="pdf") as pdf:
        assert "한글HWP변환12345" in normalized("".join(page.get_text() for page in pdf))
        assert len(pdf) == (2 if kind == "sections" else 1)
        assert abs(pdf[0].rect.width - 595.28) < 1
        assert not pdf.is_repaired and not pdf.is_encrypted
        if kind == "image":
            assert sum(len(page.get_image_info()) for page in pdf) >= 1
    report = client.get(job["links"]["quality"]).json()
    assert report["route"] == "hwp_cli_to_pdf" and report["output_format"] == "pdf"
    assert report["metrics"]["character_coverage"]["value"] == 1
    assert report["input_sha256"] == hashlib.sha256(before).hexdigest()
    assert source.read_bytes() == before
    space = client.app.state.jobs.space(job["job_id"]).path
    assert (space / "output/result.pdf").is_file()
    assert not (space / "output/result.docx").exists()
    assert not (space / "input").exists() and not (space / "work").exists()
    assert client.delete(job["links"]["self"]).status_code == 202
    assert client.get(job["links"]["download"]).status_code == 410


@pytest.mark.parametrize("kind,code", [("password_flag", "PASSWORD_PROTECTED"), ("distribution", "RESTRICTED_DOCUMENT"),
                                      ("header", "UNSUPPORTED_FEATURE")])
def test_protected_or_unsupported_hwp_has_no_pdf(client, hwp_samples, kind, code):
    job = wait_job(client, submit_pdf(client, hwp_samples[kind]).json()["job_id"])
    assert job["state"] == "failed" and job["error"]["code"] == code, job
    assert job["links"]["download"] is None
    assert not (client.app.state.jobs.space(job["job_id"]).path / "output").exists()


def test_pdf_endpoint_rejects_wrong_input_and_csrf(client, samples, hwp_samples):
    assert submit_pdf(client, samples["text"]).json()["error"]["code"] == "INVALID_OPTIONS"
    token = client.headers.pop("X-CSRF-Token")
    assert submit_pdf(client, hwp_samples["text"]).status_code == 403
    client.headers["X-CSRF-Token"] = token
    assert client.post("/api/v1/hwp-pdf/jobs", files={"file": ("sample.hwp", hwp_samples["text"].read_bytes())},
                       data={"mode": "balanced"}).status_code == 400
    assert not client.app.state.jobs.jobs


def test_pdf_validator_rejects_missing_text_and_images(tmp_path):
    path = tmp_path / "partial.pdf"
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((72, 72), "Hello")
        pdf.save(path)
    analysis = DocumentAnalysis(None, [], ["Hello World"], [], format="hwp")
    with pytest.raises(DomainError, match="VALIDATION_FAILED"):
        PdfQualityValidator().validate(path, analysis, 100)
    analysis.page_texts = ["Hello"]
    analysis.engine_data["image_hashes"] = ["required-image"]
    with pytest.raises(DomainError, match="VALIDATION_FAILED"):
        PdfQualityValidator().validate(path, analysis, 100)


def test_pdf_result_survives_server_restart(tmp_path, hwp_samples):
    settings = replace(Settings(), workspace=tmp_path / "jobs", allowed_hosts=("testserver",))
    with TestClient(create_app(settings)) as client:
        client.headers["X-CSRF-Token"] = client.get("/api/v1/session").json()["csrf_token"]
        job = wait_job(client, submit_pdf(client, hwp_samples["text"]).json()["job_id"])
        assert job["state"] == "succeeded", job
    with TestClient(create_app(settings)) as client:
        restored = client.get(job["links"]["self"]).json()
        assert restored["state"] == "succeeded" and restored["output_format"] == "pdf"
        assert client.get(restored["links"]["download"]).content.startswith(b"%PDF-")
