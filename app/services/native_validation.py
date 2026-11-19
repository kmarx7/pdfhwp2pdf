from collections import Counter

from app.domain.errors import DomainError
from app.quality.validator import normalized


def validate_reference_text(original, reference) -> float:
    expected = normalized("".join(original.page_texts))
    actual = normalized("".join(reference.page_texts))
    coverage = sum((Counter(expected) & Counter(actual)).values()) / max(1, len(expected))
    if not expected or coverage < 0.99:
        raise DomainError("REFERENCE_MISMATCH", "기준 PDF에서 원본 HWP의 본문을 충분히 확인하지 못했습니다.",
                          details={"character_coverage": round(coverage, 5)},
                          suggestion="같은 HWP의 전체 페이지를 한글 뷰어에서 PDF로 저장해 선택하세요. 일부 페이지만 출력한 PDF는 사용할 수 없습니다.")
    return coverage
