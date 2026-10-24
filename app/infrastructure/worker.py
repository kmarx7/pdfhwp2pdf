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

    sources = list((workspace / "input").iterdir())
    if len(sources) != 1 or sources[0].suffix not in {".pdf", ".hwp"}:
        raise DomainError("INVALID_DOCUMENT", "작업 입력 파일을 확인하지 못했습니다.", 400)
    source = sources[0]
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    emit({"stage": "analyzing"})
    if source.suffix == ".hwp":
        from app.services.hwp_analyzer import HwpAnalyzer
        analysis = HwpAnalyzer().analyze(source, workspace / "work", emit)
    else:
        analysis = DocumentAnalyzer().analyze(source, max_pages)
    emit({"stage": "converting", "pages": analysis.pages, "warnings": analysis.warnings})
    engine = ConversionDispatcher().select(analysis, ConversionOptions())
    result = engine.convert(source, analysis, ConversionOptions(), workspace / "work", emit)
    emit({"stage": "postprocessing"})
    if analysis.format == "hwp":
        from app.postprocess.hwp import HwpDocxPostProcessor
        HwpDocxPostProcessor().process(result.docx_path, analysis)
    DocxPostProcessor().process(result.docx_path)
    emit({"stage": "validating"})
    quality = QualityValidator().validate(result.docx_path, analysis)
    if hashlib.sha256(source.read_bytes()).hexdigest() != before:
        raise DomainError("VALIDATION_FAILED", "입력 복사본의 무결성 확인에 실패했습니다.")
    quality["engine"] = {"id": result.engine_id, "version": result.version}
    quality["input_sha256"] = before
    quality["fonts"] = analysis.fonts
    quality["source_format"] = analysis.format
    quality["platform"] = {"python": sys.version.split()[0], "system": sys.platform}
    output = workspace / "output/result.docx"
    result.docx_path.replace(output)
    atomic_json(workspace / "output/quality.json", quality)
    emit({"stage": "complete", "engine": quality["engine"], "pages": analysis.pages,
          "sha256": hashlib.sha256(output.read_bytes()).hexdigest()})


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
