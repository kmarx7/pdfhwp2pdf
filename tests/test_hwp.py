import copy
import hashlib
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from docx import Document
from docx.oxml.ns import qn
import pytest

from app.domain.errors import DomainError
from app.domain.models import ConversionOptions
from app.engines.hwp.cli import HwpCli
from app.engines.hwp.hwp_cli_engine import HwpCliEngine
from app.postprocess.docx import DocxPostProcessor
from app.postprocess.hwp import HwpDocxPostProcessor
from app.quality.validator import QualityValidator, normalized
from app.services.hwp_analyzer import HwpAnalyzer, guard_hwp_container
from scripts.make_test_hwps import make_test_hwps
from tests.conftest import submit, wait_job


@pytest.fixture(scope="session")
def hwp_samples(tmp_path_factory):
    assert HwpCli().available(), "HWP 통합 테스트 전에 scripts/install_hwp_engine.py를 실행하세요."
    return make_test_hwps(tmp_path_factory.mktemp("synthetic-hwp"))


@pytest.mark.parametrize("kind", ["text", "table", "merged", "image", "sections", "colored"])
def test_hwp_real_engine_download_editable_objects(client, hwp_samples, kind):
    source = hwp_samples[kind]
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    response = submit(client, source)
    assert response.status_code == 202, response.text
    assert response.json()["format"] == "hwp"
    job = wait_job(client, response.json()["job_id"])
    assert job["state"] == "succeeded", job
    assert job["engine"] == {"id": "hwp-cli", "version": "1.3.1"}
    assert job["progress"]["total_pages"] is None
    download = client.get(job["links"]["download"])
    assert download.status_code == 200
    assert download.headers["content-disposition"] == 'attachment; filename="converted.docx"'
    assert download.headers["content-type"].endswith("wordprocessingml.document")
    document = Document(BytesIO(download.content))
    text = "".join(node.text or "" for node in document.element.findall(".//" + qn("w:t")))
    assert "한글HWP변환12345" in normalized(text)
    run = next(run for para in document.paragraphs for run in para.runs if "12345" in run.text)
    assert run.bold is True and run.font.size.pt == 18 and run.font.name == "Arial"
    assert str(run.font.color.rgb) == "112233"
    assert abs(document.sections[0].page_width.pt - 595.28) < 1
    if kind in {"table", "colored"}:
        assert [[cell.text for cell in row.cells] for row in document.tables[0].rows] == [["품목", "금액"], ["사과", "100"], ["배", "200"]]
        assert abs(document.tables[0].columns[0].width.mm - 40) < 0.1
        assert abs(document.tables[0].columns[1].width.mm - 110) < 0.1
        if kind == "colored":
            assert document.tables[0].cell(0, 0)._tc.tcPr.find(qn("w:shd")).get(qn("w:fill")) == "FFFFCC"
    if kind == "merged":
        table = document.tables[0]
        assert table.cell(0, 0)._tc is table.cell(1, 0)._tc
        assert table.cell(0, 1)._tc is table.cell(0, 2)._tc
    if kind == "image":
        assert len(document.inline_shapes) == 1
        with ZipFile(BytesIO(download.content)) as package:
            assert len([name for name in package.namelist() if name.startswith("word/media/")]) == 1
    else:
        with ZipFile(BytesIO(download.content)) as package:
            assert not any(name.startswith("word/media/") for name in package.namelist())
    if kind == "sections":
        assert len(document.sections) == 2
        assert "두번째섹션의본문67890" in normalized(text)
    document.paragraphs[0].add_run("수정")
    if document.tables:
        document.tables[0].cell(0, 0).text = "셀 수정"
    saved = BytesIO()
    document.save(saved)
    saved.seek(0)
    assert "수정" in Document(saved).paragraphs[0].text
    report = client.get(job["links"]["quality"]).json()
    assert report["metrics"]["character_coverage"]["value"] == 1
    assert report["metrics"]["source_page_count"]["status"] == "not_measured"
    assert report["source_format"] == "hwp"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    workspace = client.app.state.jobs.space(job["job_id"]).path
    assert not (workspace / "input").exists() and not (workspace / "work").exists()


def test_independent_apache_hwp_fixture(client):
    source = Path(__file__).parent / "fixtures/hwp/hello_world.hwp"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == "283e16ee51834d75e22f413203549027a5d3fda39346302d9429e9732bb3a77c"
    job = wait_job(client, submit(client, source).json()["job_id"])
    assert job["state"] == "succeeded", job
    document = Document(BytesIO(client.get(job["links"]["download"]).content))
    assert "Hello" in "".join(paragraph.text for paragraph in document.paragraphs)


@pytest.mark.parametrize(("kind", "code"), [
    ("password_flag", "PASSWORD_PROTECTED"), ("distribution", "RESTRICTED_DOCUMENT"),
    ("drm", "RESTRICTED_DOCUMENT"), ("header", "UNSUPPORTED_FEATURE"),
])
def test_hwp_protection_and_unsupported_features_fail_without_output(client, hwp_samples, kind, code):
    job = wait_job(client, submit(client, hwp_samples[kind]).json()["job_id"])
    assert job["state"] == "failed", job
    assert job["error"]["code"] == code
    assert job["links"]["download"] is None
    assert client.get(job["links"]["self"] + "/download").status_code == 409
    assert not (client.app.state.jobs.space(job["job_id"]).path / "output").exists()


def test_hwp_invalid_and_mismatched_files(client, hwp_samples, samples):
    assert submit(client, hwp_samples["text"], "wrong.pdf").json()["error"]["code"] == "FORMAT_MISMATCH"
    assert submit(client, samples["text"], "wrong.hwp").json()["error"]["code"] == "FORMAT_MISMATCH"
    assert client.post("/api/v1/jobs", files={"file": ("invalid.hwp", b"invalid")}).status_code == 400
    response = client.post("/api/v1/jobs", files={"file": ("broken.hwp", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"X" * 512)})
    job = wait_job(client, response.json()["job_id"])
    assert job["error"]["code"] == "INVALID_DOCUMENT"


def test_old_hwp_variant_is_explicitly_rejected(client):
    response = client.post("/api/v1/jobs", files={"file": ("old.hwp", b"HWP Document File V3.00" + b"X" * 512)})
    job = wait_job(client, response.json()["job_id"])
    assert job["error"]["code"] == "UNSUPPORTED_VARIANT"


def test_hwp_compression_guard_and_missing_engine(hwp_samples, monkeypatch, tmp_path):
    import app.services.hwp_analyzer as analyzer
    monkeypatch.setattr(analyzer, "MAX_STREAM", 300)
    with pytest.raises(DomainError) as error:
        guard_hwp_container(hwp_samples["text"])
    assert error.value.code == "ARCHIVE_LIMIT_EXCEEDED"
    assert not HwpCli(binary=tmp_path / "missing").available()


@pytest.mark.parametrize("kind", ["table", "merged", "image"])
def test_hwp_result_structure_loss_is_rejected(hwp_samples, tmp_path, kind):
    analysis = HwpAnalyzer().analyze(hwp_samples[kind], tmp_path)
    result = HwpCliEngine().convert(hwp_samples[kind], analysis, ConversionOptions(), tmp_path, lambda event: None)
    HwpDocxPostProcessor().process(result.docx_path, analysis)
    DocxPostProcessor().process(result.docx_path)
    QualityValidator().validate(result.docx_path, analysis)
    broken = copy.deepcopy(analysis)
    if kind == "image":
        broken.engine_data["image_hashes"] = ["wrong"]
    else:
        broken.engine_data["tables"][0]["cells"][0]["row_span"] += 1
    with pytest.raises(DomainError) as error:
        QualityValidator().validate(result.docx_path, broken)
    assert error.value.code == "VALIDATION_FAILED"


def test_hwp_engine_failure_does_not_publish_result(hwp_samples, tmp_path, monkeypatch):
    analysis = HwpAnalyzer().analyze(hwp_samples["text"], tmp_path)

    def fail(*args, **kwargs):
        raise DomainError("ENGINE_FAILED", "테스트 엔진 실패")

    monkeypatch.setattr(HwpCli, "run", fail)
    with pytest.raises(DomainError):
        HwpCliEngine().convert(hwp_samples["text"], analysis, ConversionOptions(), tmp_path, lambda event: None)
    assert not (tmp_path / "converted.tmp.docx").exists()


def test_hwp_binary_integrity_and_installer_rejects_invalid_archive(tmp_path):
    from scripts.install_hwp_engine import install
    fake = tmp_path / "hwp"
    fake.write_bytes(b"different binary")
    fake.chmod(0o755)
    assert not HwpCli(binary=fake).available()
    archive = tmp_path / "invalid.tar.gz"
    archive.write_bytes(b"invalid archive")
    with pytest.raises(ValueError, match="SHA-256"):
        install(archive)
