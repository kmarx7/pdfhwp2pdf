from collections import Counter
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
            return {
                "schema_version": "1.0", "validation_status": "structural_pass",
                "metrics": {
                    "editable_text": {"status": "measured", "value": True, "method": "ooxml_text_nodes"},
                    "character_coverage": {"status": "measured", "value": round(coverage, 5),
                                           "method": "normalized_character_multiset", "reading_order_verified": False},
                    "word_table_count": {"status": "measured", "value": len(document.tables)},
                    "source_page_count": {"status": "measured", "value": analysis.pages},
                    "cer": {"status": "not_measured", "value": None, "reason": "ground_truth_missing"},
                    "visual_ssim": {"status": "not_measured", "value": None, "reason": "renderer_not_run"},
                },
                "manual_review": {"word_edit": "not_performed"},
                "warnings": analysis.warnings,
                "quality_scope": "structural_checks_only",
            }
        except Exception as exc:
            raise DomainError("VALIDATION_FAILED", "결과의 편집 가능한 텍스트 또는 표 구조 검증을 통과하지 못했습니다.",
                              suggestion="부분 결과는 제공하지 않습니다. 다른 PDF로 시도하세요.") from exc
