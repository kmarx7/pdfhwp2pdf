from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ConversionOptions:
    mode: str = "balanced"
    ocr: str = "off"


@dataclass
class DocumentAnalysis:
    pages: int | None
    page_sizes: list[tuple[float, float]]
    page_texts: list[str]
    fonts: list[str]
    table_count: int = 0
    warnings: list[str] = field(default_factory=list)
    format: str = "pdf"
    engine_data: dict = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class EngineResult:
    output_path: Path
    engine_id: str
    version: str
    output_format: str = "docx"

    @property
    def docx_path(self) -> Path:
        """기존 DOCX 엔진 호출부 호환용. 새 코드는 output_path를 사용한다."""
        return self.output_path
