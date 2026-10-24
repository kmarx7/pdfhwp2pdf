from app.domain.errors import DomainError
from app.domain.models import ConversionOptions, DocumentAnalysis
from app.engines.base import ConversionEngine
from app.engines.pdf.pdf2docx_engine import Pdf2DocxEngine


class EngineRegistry:
    def __init__(self):
        self.engines: list[ConversionEngine] = [Pdf2DocxEngine()]

    def probe(self) -> list[dict]:
        return [engine.probe() for engine in self.engines]


class ConversionDispatcher:
    def select(self, analysis: DocumentAnalysis, options: ConversionOptions) -> ConversionEngine:
        for engine in EngineRegistry().engines:
            if engine.can_convert(analysis, options):
                if engine.probe()["availability"] != "unavailable":
                    return engine
        raise DomainError("ENGINE_UNAVAILABLE", "사용 가능한 PDF 변환 엔진이 없습니다.", 503)
