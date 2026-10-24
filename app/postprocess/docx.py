from pathlib import Path

from docx import Document


class DocxPostProcessor:
    def process(self, path: Path) -> None:
        """레이아웃을 재작성하지 않고 생성기 개인 정보만 정리한다."""
        document = Document(path)
        document.core_properties.author = ""
        document.core_properties.last_modified_by = ""
        document.core_properties.comments = ""
        document.save(path)
