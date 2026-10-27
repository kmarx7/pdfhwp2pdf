"""요청 프로세스와 격리된 변환. stdout은 본문 없는 JSON 이벤트만 전달한다."""
import contextlib
import hashlib
import json
import logging
import os
import signal
from pathlib import Path
import sys
import threading
import time

from app.domain.errors import DomainError
from app.domain.models import ConversionOptions
from app.infrastructure.workspace import atomic_json


def heartbeat(parent: int) -> None:
    while True:
        time.sleep(1)
        if os.getppid() != parent:
            if os.getpgrp() == os.getpid():
                os.killpg(os.getpgrp(), signal.SIGTERM)
            os._exit(1)


def run(workspace: Path, max_pages: int, emit) -> None:
    # 엔진은 import 시 logging 설정을 바꾸므로 라이브러리 로그를 전부 차단한다.
    logging.disable(logging.CRITICAL)
    from app.services.analyzer import DocumentAnalyzer
    from app.services.dispatcher import ConversionDispatcher
    from app.postprocess.docx import DocxPostProcessor
    from app.quality.validator import QualityValidator

    mode = json.loads((workspace / "meta.json").read_text()).get("mode", "balanced")
    options = ConversionOptions(mode=mode)
    inputs = list((workspace / "input").iterdir())
    sources = [path for path in inputs if path.name in {"source.pdf", "source.hwp"}]
    if len(sources) != 1:
        raise DomainError("INVALID_DOCUMENT", "작업 입력 파일을 확인하지 못했습니다.", 400)
    source = sources[0]
    expected = {source.name}
    if mode == "native_embedded" and source.suffix == ".hwp":
        expected.add("reference.pdf")
    if {path.name for path in inputs} != expected or any(path.is_symlink() or not path.is_file() for path in inputs):
        raise DomainError("INVALID_DOCUMENT", "작업 입력 구성이나 경로가 올바르지 않습니다.", 400)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    emit({"stage": "analyzing"})
    reference_hash = None
    reference_coverage = None
    conversion_source = source
    if mode == "native_embedded":
        if source.suffix == ".hwp":
            from app.services.hwp_analyzer import HwpAnalyzer
            from app.services.native_validation import validate_reference_text
            original = HwpAnalyzer().analyze(source, workspace / "work", emit)
            conversion_source = workspace / "input/reference.pdf"
            analysis = DocumentAnalyzer().analyze(conversion_source, max_pages)
            reference_coverage = validate_reference_text(original, analysis)
            reference_hash = hashlib.sha256(conversion_source.read_bytes()).hexdigest()
        else:
            analysis = DocumentAnalyzer().analyze(source, max_pages)
        settings = json.loads((workspace / "work/native-options.json").read_text())
        analysis.engine_data["native_font_dirs"] = settings["font_dirs"]
    elif source.suffix == ".hwp":
        from app.services.hwp_analyzer import HwpAnalyzer
        analysis = HwpAnalyzer().analyze(source, workspace / "work", emit)
    else:
        analysis = DocumentAnalyzer().analyze(source, max_pages)
    emit({"stage": "converting", "pages": analysis.pages, "warnings": analysis.warnings})
    if mode == "hwp_pdf":
        settings = json.loads((workspace / "work/pdf-options.json").read_text())
        analysis.engine_data["pdf_font_dirs"] = settings["font_dirs"]
    engine = ConversionDispatcher().select(analysis, options)
    result = engine.convert(conversion_source, analysis, options, workspace / "work", emit)
    emit({"stage": "postprocessing"})
    if analysis.format == "hwp" and mode != "hwp_pdf":
        from app.postprocess.hwp import HwpDocxPostProcessor
        HwpDocxPostProcessor().process(result.docx_path, analysis)
    if mode not in {"native_embedded", "hwp_pdf"}:
        DocxPostProcessor().process(result.docx_path)
    emit({"stage": "validating"})
    if mode == "hwp_pdf":
        from app.quality.pdf_validator import PdfQualityValidator
        quality = PdfQualityValidator().validate(result.output_path, analysis, max_pages)
    else:
        quality = QualityValidator().validate(result.docx_path, analysis)
    if mode == "native_embedded":
        quality["route"] = "native_reference_pdf_to_docx_with_fonts"
        quality["embedded_fonts"] = analysis.engine_data["embedded_fonts"]
        if reference_hash:
            if hashlib.sha256(conversion_source.read_bytes()).hexdigest() != reference_hash:
                raise DomainError("VALIDATION_FAILED", "기준 PDF 무결성 확인에 실패했습니다.")
            quality["reference_pdf_sha256"] = reference_hash
            quality["metrics"]["hwp_reference_text_coverage"] = {"status": "measured", "value": reference_coverage, "method": "normalized_character_multiset"}
            quality["metrics"]["reference_pdf_page_count"] = {"status": "measured", "value": analysis.pages}
            quality["metrics"]["source_page_count"] = {"status": "not_measured", "value": None}
    if hashlib.sha256(source.read_bytes()).hexdigest() != before:
        raise DomainError("VALIDATION_FAILED", "입력 복사본의 무결성 확인에 실패했습니다.")
    quality["engine"] = {"id": result.engine_id, "version": result.version}
    quality["input_sha256"] = before
    quality["fonts"] = analysis.fonts
    quality["source_format"] = source.suffix[1:]
    quality["platform"] = {"python": sys.version.split()[0], "system": sys.platform}
    expected_format = "pdf" if mode == "hwp_pdf" else "docx"
    if result.output_format != expected_format:
        raise DomainError("VALIDATION_FAILED", "요청한 출력 형식과 결과가 다릅니다.")
    output = workspace / f"output/result.{expected_format}"
    result.output_path.replace(output)
    atomic_json(workspace / "output/quality.json", quality)
    pages = quality["metrics"]["output_page_count"]["value"] if mode == "hwp_pdf" else analysis.pages
    emit({"stage": "complete", "engine": quality["engine"], "pages": pages,
          "sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "warnings": analysis.warnings})


def main() -> int:
    workspace = Path(sys.argv[1]).resolve()
    parent = int(sys.argv[3])
    threading.Thread(target=heartbeat, args=(parent,), daemon=True).start()
    # 엔진의 print를 프로토콜과 분리한다.
    protocol = sys.stdout

    def emit(event):
        protocol.write(json.dumps(event, ensure_ascii=False) + "\n")
        protocol.flush()

    try:
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            run(workspace, int(sys.argv[2]), emit)
        return 0
    except DomainError as exc:
        emit({"stage": "failed", "error": exc.as_dict()})
    except Exception:
        emit({"stage": "failed", "error": DomainError("ENGINE_FAILED", "변환 프로세스에서 오류가 발생했습니다.").as_dict()})
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
