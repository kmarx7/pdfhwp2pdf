from collections import Counter

import pymupdf

from app.domain.errors import DomainError
from app.quality.validator import normalized
from app.services.analyzer import DocumentAnalyzer


class PdfQualityValidator:
    def validate(self, path, original, max_pages):
        generated = DocumentAnalyzer().analyze(path, max_pages)
        expected = Counter(normalized("".join(original.page_texts)))
        actual = Counter(normalized("".join(generated.page_texts)))
        coverage = sum((expected & actual).values()) / max(1, sum(expected.values()))
        if not expected or coverage < 0.99:
            raise DomainError("VALIDATION_FAILED", "생성한 PDF에서 원본 HWP 본문을 충분히 확인하지 못했습니다.",
                              details={"character_coverage": round(coverage, 5)},
                              suggestion="본문이 누락된 부분 결과는 제공하지 않습니다. 한글 뷰어의 PDF 인쇄를 사용해 주세요.")
        with pymupdf.open(path) as pdf:
            images = sum(len(page.get_image_info()) for page in pdf)
        if original.engine_data.get("image_hashes") and not images:
            raise DomainError("VALIDATION_FAILED", "생성한 PDF에서 원본의 이미지를 확인하지 못했습니다.")
        return {"schema_version": "1.0", "validation_status": "structural_pass",
                "route": "hwp_cli_to_pdf", "output_format": "pdf", "quality_scope": "text_and_image_presence_checks_only",
                "metrics": {"character_coverage": {"status": "measured", "value": round(coverage, 5),
                                                   "method": "normalized_character_multiset", "reading_order_verified": False},
                            "source_page_count": {"status": "not_measured", "value": None},
                            "output_page_count": {"status": "measured", "value": generated.pages},
                            "output_image_count": {"status": "measured", "value": images},
                            "visual_ssim": {"status": "not_measured", "value": None}},
                "warnings": original.warnings, "manual_review": {"visual_review": "not_performed"}}
