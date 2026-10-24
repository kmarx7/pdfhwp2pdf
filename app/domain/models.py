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
    docx_path: Path
    engine_id: str
    version: str
