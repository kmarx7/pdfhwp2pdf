from pathlib import Path

from app.domain.models import ConversionOptions, EngineResult
from app.engines.pdf.pdf2docx_engine import Pdf2DocxEngine
from app.postprocess.docx import DocxPostProcessor
from app.postprocess.embedded_fonts import embed_local_fonts


class NativeEmbeddedEngine:
    def probe(self):
        return Pdf2DocxEngine().probe() | {"engine_id": "native-pdf-embedded", "modes": ["native_embedded"]}

    def can_convert(self, analysis, options):
        return analysis.format == "pdf" and options.mode == "native_embedded" and options.ocr == "off"

    def convert(self, source, analysis, options, workspace, emit):
        raw = Pdf2DocxEngine().convert(source, analysis, ConversionOptions(), workspace, emit)
        emit({"stage": "postprocessing"})
        DocxPostProcessor().process(raw.docx_path)
        output = workspace / "native-embedded.docx"
        folders = [Path(path) for path in analysis.engine_data["native_font_dirs"]]
        analysis.engine_data["embedded_fonts"] = embed_local_fonts(raw.docx_path, output, folders)
        analysis.warnings.append("native-embedded 경로: 기준 PDF의 전체 페이지를 텍스트·표로 변환하고 로컬 글꼴을 포함했습니다. Word의 페이지 수·줄바꿈은 원본과 다를 수 있습니다.")
        return EngineResult(output, "native-pdf-embedded", raw.version)
