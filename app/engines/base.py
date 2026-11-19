from pathlib import Path
from typing import Callable, Protocol

from app.domain.models import ConversionOptions, DocumentAnalysis, EngineResult


class ConversionEngine(Protocol):
    def probe(self) -> dict: ...

    def can_convert(self, analysis: DocumentAnalysis, options: ConversionOptions) -> bool: ...

    def convert(self, source: Path, analysis: DocumentAnalysis, options: ConversionOptions,
                workspace: Path, emit: Callable[[dict], None]) -> EngineResult: ...
