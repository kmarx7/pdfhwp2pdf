"""환경·후보 import 검사. --smoke는 합성 영문 PDF의 텍스트 보존만 확인한다."""

from __future__ import annotations

import argparse
import contextlib
import importlib
import importlib.metadata
import io
import json
import platform
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


PACKAGES = {
    "PyMuPDF": "pymupdf",
    "pdf2docx": "pdf2docx",
    "python-docx": "docx",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "python-multipart": "python_multipart",
    "pytest": "pytest",
    "httpx": "httpx",
    "defusedxml": "defusedxml",
    "olefile": "olefile",
}


def probe_packages() -> dict:
    """배포 버전과 실제 import 결과를 각각 기록한다."""
    results = {}
    for distribution, module in PACKAGES.items():
        item = {"version": None, "import": "not_attempted"}
        try:
            item["version"] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            item["import"] = "missing"
            results[distribution] = item
            continue
        try:
            # 라이브러리가 출력해도 stdout의 JSON 형식을 깨지 않게 한다.
            with contextlib.redirect_stdout(io.StringIO()):
                importlib.import_module(module)
            item["import"] = "ok"
        except Exception as exc:
            # 예외 문자열에는 로컬 경로가 있을 수 있으므로 타입만 기록한다.
            item["import"] = "failed"
            item["error_type"] = type(exc).__name__
        results[distribution] = item
    return results


def smoke_pdf(project_root: Path) -> dict:
    """임시 합성 파일만 사용하고 정상·실패 모두 자동 정리한다."""
    import pymupdf
    from docx import Document
    from pdf2docx import Converter

    marker = "Editable document smoke test 12345"
    with tempfile.TemporaryDirectory(prefix="pdfhwp-probe-", dir=project_root) as folder:
        source = Path(folder) / "synthetic.pdf"
        output = Path(folder) / "synthetic.docx"
        with pymupdf.open() as pdf:
            page = pdf.new_page(width=595, height=842)
            page.insert_text((72, 72), marker, fontsize=12)
            pdf.save(source)
        converter = Converter(str(source))
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                converter.convert(str(output), start=0, end=1)
        finally:
            converter.close()
        document = Document(output)
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        if marker not in text:
            raise ValueError("Synthetic marker is missing from DOCX paragraphs")
        return {
            "status": "passed",
            "input_kind": "synthetic_single_page_english_pdf",
            "checks": ["docx_reopened", "marker_in_paragraph_text"],
            "real_document_quality_verified": False,
            "temporary_files": "deleted_on_exit",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[1]
    local_venv = Path(sys.prefix).resolve() == (project_root / ".venv").resolve()
    packages = probe_packages()
    ready = all(item["import"] == "ok" for item in packages.values())
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "system": platform.system(),
        "macos": platform.mac_ver()[0] or None,
        "machine": platform.machine(),
        "project_venv": local_venv,
        "python_3_11": sys.version_info[:2] == (3, 11),
        "packages": packages,
        "smoke": {"status": "not_requested"},
        "real_document_quality_verified": False,
    }
    exit_code = 0 if ready and local_venv and report["python_3_11"] else 2
    if args.smoke:
        required = ("PyMuPDF", "pdf2docx", "python-docx")
        if not local_venv or not report["python_3_11"]:
            report["smoke"] = {"status": "not_run", "reason": "project_python_required"}
        elif any(packages[name]["import"] != "ok" for name in required):
            report["smoke"] = {"status": "not_run", "reason": "dependencies_missing_or_broken"}
        else:
            try:
                report["smoke"] = smoke_pdf(project_root)
            except Exception as exc:
                report["smoke"] = {"status": "failed", "error_type": type(exc).__name__}
                exit_code = 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
