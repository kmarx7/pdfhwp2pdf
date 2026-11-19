"""한글 뷰어에서 출력한 PDF를 글꼴 포함 편집용 DOCX로 변환한다. HWP GUI 자동화는 하지 않는다."""
import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.domain.errors import DomainError
from app.domain.models import ConversionOptions
from app.engines.pdf.pdf2docx_engine import Pdf2DocxEngine
from app.postprocess.docx import DocxPostProcessor
from app.postprocess.embedded_fonts import embed_local_fonts
from app.quality.validator import QualityValidator
from app.services.analyzer import DocumentAnalyzer


def convert(source: Path, target: Path, font_dirs: list[Path]) -> dict:
    source, target = source.resolve(), target.resolve()
    report_path = target.with_suffix(".quality.json")
    if target.exists() or report_path.exists():
        raise FileExistsError("출력 DOCX 또는 품질 보고서가 이미 존재합니다. 다른 출력 이름을 지정하세요.")
    if target.suffix.lower() != ".docx":
        raise DomainError("INVALID_OPTIONS", "출력 확장자는 .docx여야 합니다.")
    if source.stat().st_size > 30 * 1024 * 1024:
        raise DomainError("FILE_TOO_LARGE", "기준 PDF는 30 MiB까지 지원합니다.")
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    target.parent.mkdir(parents=True, exist_ok=True)
    published = False
    report_created = False
    try:
        with tempfile.TemporaryDirectory(prefix=".native-pdf-", dir=target.parent) as folder:
            workspace = Path(folder)
            analysis = DocumentAnalyzer().analyze(source)
            result = Pdf2DocxEngine().convert(source, analysis, ConversionOptions(), workspace, lambda _: None)
            DocxPostProcessor().process(result.docx_path)
            embedded = workspace / "embedded.docx"
            fonts = embed_local_fonts(result.docx_path, embedded, font_dirs)
            report = QualityValidator().validate(embedded, analysis)
            if hashlib.sha256(source.read_bytes()).hexdigest() != before:
                raise DomainError("VALIDATION_FAILED", "입력 PDF 무결성 확인에 실패했습니다.")
            report.update(input_sha256=before, route="native_reference_pdf_to_docx_with_fonts", fonts=fonts,
                          output_sha256=hashlib.sha256(embedded.read_bytes()).hexdigest())
            # 같은 폴더의 임시 파일을 원자적으로 연결한다. 기존 결과를 덮어쓰지 않는다.
            os.link(embedded, target)
            published = True
            with report_path.open("x") as stream:
                report_created = True
                json.dump(report, stream, ensure_ascii=False, indent=2)
        return report
    except Exception:
        if published:
            target.unlink(missing_ok=True)
        if report_created:
            report_path.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--font-dir", action="append", type=Path)
    args = parser.parse_args()
    folders = args.font_dir or [Path("/Applications/Hancom Office HWP Viewer.app/Contents/Resources/Hnc/Shared/TTF/Install"), Path.home() / "Library/Fonts"]
    logging.disable(logging.CRITICAL)
    try:
        report = convert(args.source, args.output, folders)
    except DomainError as error:
        print(json.dumps(error.as_dict(), ensure_ascii=False))
        return 1
    except (OSError, ValueError) as error:
        print(json.dumps({"error": type(error).__name__, "message": "파일을 읽거나 저장하지 못했습니다. 입력·출력 경로와 기존 파일을 확인하세요."}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "structural_pass", "embedded_fonts": report["fonts"]["embedded_font_count"],
                      "visual_fidelity_verified": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
