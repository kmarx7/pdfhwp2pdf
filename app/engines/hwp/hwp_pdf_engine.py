from pathlib import Path

import pymupdf

from app.domain.errors import DomainError
from app.domain.models import EngineResult
from app.engines.hwp.cli import HwpCli, VERSION


class HwpPdfEngine:
    def probe(self):
        available = HwpCli().available()
        return {"engine_id": "hwp-cli-pdf", "version": VERSION if available else None,
                "availability": "experimental" if available else "unavailable",
                "modes": ["hwp_pdf"] if available else [], "output_format": "pdf",
                "reason_code": "REAL_DOCUMENT_QUALITY_UNVERIFIED" if available else "DEPENDENCY_MISSING"}

    def can_convert(self, analysis, options):
        return analysis.format == "hwp" and options.mode == "hwp_pdf" and options.ocr == "off"

    def convert(self, source, analysis, options, workspace, emit):
        if not self.can_convert(analysis, options):
            raise DomainError("INVALID_OPTIONS", "HWP → PDF 변환 옵션이 올바르지 않습니다.")
        raw, output = workspace / "rendered.pdf", workspace / "converted.pdf"
        arguments = ["convert", str(source), "-o", str(raw), "--to", "pdf"]
        for folder in analysis.engine_data.get("pdf_font_dirs", []):
            if Path(folder).is_dir():
                arguments.extend(["--font-dir", folder])
        HwpCli(emit=emit).run(arguments, workspace)
        if not raw.is_file() or raw.stat().st_size == 0:
            raise DomainError("ENGINE_FAILED", "HWP 엔진이 PDF를 생성하지 못했습니다.")
        emit({"stage": "postprocessing"})
        try:
            with pymupdf.open(raw) as pdf:
                pdf.set_metadata({})
                pdf.save(output)
        except Exception as error:
            raise DomainError("VALIDATION_FAILED", "생성한 PDF를 다시 열지 못했습니다.") from error
        analysis.warnings = ["실험적인 HWP → PDF 변환입니다. 한글 뷰어의 PDF 인쇄와 다른 엔진을 사용하므로 글꼴·표·쪽 나눔이 달라질 수 있습니다.",
                             "본문 문자 포함률은 읽기 순서·표 배치·시각 유사도 일치를 보장하지 않습니다."]
        return EngineResult(output, "hwp-cli-pdf", VERSION, "pdf")
