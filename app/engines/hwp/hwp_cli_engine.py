from pathlib import Path
from typing import Callable

from app.domain.errors import DomainError
from app.domain.models import ConversionOptions, DocumentAnalysis, EngineResult
from app.engines.hwp.cli import HwpCli, VERSION


class HwpCliEngine:
    def probe(self) -> dict:
        available = HwpCli().available()
        return {"engine_id": "hwp-cli", "version": VERSION if available else None,
                "availability": "experimental" if available else "unavailable",
                "modes": ["balanced"] if available else [],
                "reason_code": "REAL_DOCUMENT_QUALITY_UNVERIFIED" if available else "DEPENDENCY_MISSING",
                "scope": "hwp5_text_tables_inline_images"}

    def can_convert(self, analysis: DocumentAnalysis, options: ConversionOptions) -> bool:
        return analysis.format == "hwp" and options.mode == "balanced" and options.ocr == "off"

    def convert(self, source: Path, analysis: DocumentAnalysis, options: ConversionOptions,
                workspace: Path, emit: Callable[[dict], None]) -> EngineResult:
        if not self.can_convert(analysis, options):
            raise DomainError("INVALID_OPTIONS", "지원하지 않는 HWP 변환 옵션입니다.")
        output = workspace / "converted.tmp.docx"
        # --strict는 DOCX 손실을 검사하지 않는다. HwpAnalyzer와 결과 validator가
        # 별도로 미지원 control·본문·표·이미지 누락을 거부한다.
        HwpCli(emit=emit).run(["convert", str(source), "-o", str(output), "--to", "docx"], workspace)
        if not output.is_file() or output.stat().st_size == 0:
            raise DomainError("ENGINE_FAILED", "HWP 변환 엔진이 DOCX를 생성하지 못했습니다.")
        return EngineResult(output, "hwp-cli", VERSION)
