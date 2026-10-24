from importlib.metadata import version
from pathlib import Path
from typing import Callable

from app.domain.errors import DomainError
from app.domain.models import ConversionOptions, DocumentAnalysis, EngineResult


class Pdf2DocxEngine:
    def probe(self) -> dict:
        try:
            import pymupdf  # noqa: F401
            from pdf2docx import Converter  # noqa: F401
            return {"engine_id": "pdf2docx", "version": version("pdf2docx"),
                    "availability": "experimental", "modes": ["balanced"],
                    "reason_code": "REAL_DOCUMENT_QUALITY_UNVERIFIED"}
        except (ImportError, OSError):
            return {"engine_id": "pdf2docx", "version": None,
                    "availability": "unavailable", "modes": [],
                    "reason_code": "DEPENDENCY_MISSING"}

    def can_convert(self, analysis: DocumentAnalysis, options: ConversionOptions) -> bool:
        return analysis.format == "pdf" and options.mode == "balanced" and options.ocr == "off"

    def convert(self, source: Path, analysis: DocumentAnalysis, options: ConversionOptions,
                workspace: Path, emit: Callable[[dict], None]) -> EngineResult:
        if not self.can_convert(analysis, options):
            raise DomainError("INVALID_OPTIONS", "지원하지 않는 변환 옵션입니다.")
        from pdf2docx import Converter
        from importlib import import_module
        from app.engines.pdf.font_compat import SafeFonts

        # 변환은 단일 격리 worker에서 실행한다. 설치 패키지 파일은 수정하지 않는다.
        pages_module = import_module("pdf2docx.page.Pages")
        original_fonts = pages_module.Fonts
        pages_module.Fonts = SafeFonts

        output = workspace / "converted.tmp.docx"
        converter = None
        try:
            converter = Converter(str(source))
            # pdf2docx는 일부 페이지 오류를 무시할 수 있다. 반드시 실패로 전파한다.
            converter.convert(str(output), start=0, end=analysis.pages,
                              multi_processing=False, ignore_page_error=False)
            if not output.is_file() or output.stat().st_size == 0:
                raise DomainError("ENGINE_FAILED", "변환 엔진이 DOCX 파일을 생성하지 못했습니다.")
            return EngineResult(output, "pdf2docx", version("pdf2docx"))
        except DomainError:
            raise
        except Exception as exc:
            raise DomainError("ENGINE_FAILED", "PDF 변환 중 오류가 발생했습니다.",
                              suggestion="다른 PDF로 시도하거나 원본을 다시 PDF로 저장해 보세요.") from exc
        finally:
            pages_module.Fonts = original_fonts
            if converter is not None:
                converter.close()
