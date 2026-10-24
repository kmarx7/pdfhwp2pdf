from collections import Counter
import hashlib
from pathlib import Path
import unicodedata
from zipfile import ZipFile

from defusedxml import ElementTree
from docx import Document

from app.domain.errors import DomainError
from app.domain.models import DocumentAnalysis

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def normalized(text: str) -> str:
    return "".join(unicodedata.normalize("NFC", text).split())


class QualityValidator:
    def validate(self, path: Path, analysis: DocumentAnalysis) -> dict:
        try:
            with ZipFile(path) as package:
                if package.testzip() is not None:
                    raise ValueError("corrupt zip")
                root = ElementTree.fromstring(package.read("word/document.xml"))
            document = Document(path)
            nodes = root.findall(f".//{W}t")
            actual = normalized("".join(node.text or "" for node in nodes))
            expected = normalized("".join(analysis.page_texts))
            if not actual:
                raise ValueError("no visible text")
            for run in root.findall(f".//{W}r"):
                for tag in ("vanish", "webHidden"):
                    flag = run.find(f"{W}rPr/{W}{tag}")
                    if flag is not None and flag.get(f"{W}val", "true") not in {"0", "false", "off"}:
                        raise ValueError("hidden text")
                size = run.find(f"{W}rPr/{W}sz")
                if size is not None and int(size.get(f"{W}val", "0")) <= 1:
                    raise ValueError("zero size text")
            # 읽기 순서는 증명하지 않지만 조용한 본문 누락과 중복은 거부한다.
            expected_counts, actual_counts = Counter(expected), Counter(actual)
            matched = sum((expected_counts & actual_counts).values())
            coverage = matched / max(1, len(expected))
            excess = sum((actual_counts - expected_counts).values()) / max(1, len(expected))
            if coverage < 0.99 or excess > 0.01:
                raise ValueError("text loss or duplication")
            if analysis.table_count and not document.tables:
                raise ValueError("tables missing")
            if not document.sections:
                raise ValueError("sections missing")
            if analysis.format == "hwp":
                self.validate_hwp_structure(path, root, document, analysis)
            return {
                "schema_version": "1.0", "validation_status": "structural_pass",
                "metrics": {
                    "editable_text": {"status": "measured", "value": True, "method": "ooxml_text_nodes"},
                    "character_coverage": {"status": "measured", "value": round(coverage, 5),
                                           "method": "normalized_character_multiset", "reading_order_verified": False},
                    "word_table_count": {"status": "measured", "value": len(document.tables)},
                    "source_page_count": {"status": "measured" if analysis.pages is not None else "not_measured",
                                          "value": analysis.pages},
                    "cer": {"status": "not_measured", "value": None, "reason": "ground_truth_missing"},
                    "visual_ssim": {"status": "not_measured", "value": None, "reason": "renderer_not_run"},
                },
                "manual_review": {"word_edit": "not_performed"},
                "warnings": analysis.warnings,
                "quality_scope": "structural_checks_only",
            }
        except Exception as exc:
            raise DomainError("VALIDATION_FAILED", "결과의 편집 가능한 텍스트 또는 표 구조 검증을 통과하지 못했습니다.",
                              suggestion="부분 결과는 제공하지 않습니다. 다른 문서로 시도하세요.") from exc

    @staticmethod
    def validate_hwp_structure(path: Path, root, document, analysis: DocumentAnalysis) -> None:
        actual_tables = root.findall(f".//{W}tbl")
        expected_tables = analysis.engine_data["tables"]
        if len(actual_tables) != len(expected_tables):
            raise ValueError("HWP table count changed")
        for table, expected in zip(actual_tables, expected_tables):
            rows = table.findall(f"{W}tr")
            grid = table.findall(f"{W}tblGrid/{W}gridCol")
            if len(rows) != expected["rows"] or len(grid) != expected["cols"]:
                raise ValueError("HWP table grid changed")
            if "column_widths" in expected:
                if any(abs(int(column.get(f"{W}w")) - width / 5) > 1
                       for column, width in zip(grid, expected["column_widths"])):
                    raise ValueError("HWP column widths changed")
            cells, active = [], {}
            for row_index, row in enumerate(rows):
                column = 0
                for cell in row.findall(f"{W}tc"):
                    span = cell.find(f"{W}tcPr/{W}gridSpan")
                    width = int(span.get(f"{W}val")) if span is not None else 1
                    merge = cell.find(f"{W}tcPr/{W}vMerge")
                    if merge is not None and merge.get(f"{W}val") != "restart":
                        if column not in active:
                            raise ValueError("Broken vertical merge")
                        active[column]["row_span"] += 1
                    else:
                        item = {"row": row_index, "col": column, "row_span": 1, "col_span": width}
                        cells.append(item)
                        if merge is not None:
                            active[column] = item
                        else:
                            active.pop(column, None)
                    column += width
                if column != expected["cols"]:
                    raise ValueError("Incomplete table grid")
            key = lambda item: tuple(item[name] for name in ("row", "col", "row_span", "col_span"))
            if sorted(map(key, cells)) != sorted(map(key, expected["cells"])):
                raise ValueError("HWP cell merges changed")
        with ZipFile(path) as package:
            images = [hashlib.sha256(package.read(name)).hexdigest()
                      for name in package.namelist() if name.startswith("word/media/")]
        if Counter(images) != Counter(analysis.engine_data["image_hashes"]):
            raise ValueError("HWP images missing or changed")
        if len(document.sections) != analysis.engine_data["sections"]:
            raise ValueError("HWP section count changed")
        for section, (width, height) in zip(document.sections, analysis.page_sizes):
            if abs(section.page_width.pt - width) > 1 or abs(section.page_height.pt - height) > 1:
                raise ValueError("HWP page size changed")
