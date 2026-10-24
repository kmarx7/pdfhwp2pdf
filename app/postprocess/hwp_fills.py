"""HWP 셀 배경의 제한된 Word 매핑. 그라데이션 근사는 반드시 경고와 함께 쓴다."""
from app.domain.errors import DomainError


def colorref(value: int) -> str:
    return f"{value & 255:02X}{(value >> 8) & 255:02X}{(value >> 16) & 255:02X}"


def resolve_fill(fill: dict) -> dict:
    kind = fill.get("fill_type", 0)
    if kind not in (0, 1, 4) or fill.get("hatch"):
        raise DomainError("UNSUPPORTED_FEATURE", "그림·무늬 또는 복합 채우기 표 배경은 아직 지원하지 않습니다.",
                          suggestion="다른 파일로 시도하거나 원본의 표 배경을 확인하세요. 같은 파일 재시도로 해결되지 않습니다.")
    color = fill.get("bg_color") if kind == 1 else None
    approximation = None
    if kind == 4:
        gradient = fill.get("gradient") or {}
        stops = gradient.get("stops", [])
        if gradient.get("radial") is not False or len(stops) != 2 or [s[0] for s in stops] != [0, 1]:
            raise DomainError("UNSUPPORTED_FEATURE", "현재 두 색상의 선형 그라데이션만 단색 근사를 지원합니다.")
        colors = [stop[1] for stop in stops]
        if any(not isinstance(c, int) or not 0 <= c <= 0xFFFFFF for c in colors):
            raise DomainError("INVALID_DOCUMENT", "표 그라데이션 색상 값이 올바르지 않습니다.")
        color = sum(round(sum((c >> shift) & 255 for c in colors) / 2) << shift for shift in (0, 8, 16))
        approximation = "linear_gradient_midpoint"
    return {"background": None if color in (None, 0xFFFFFFFF) else colorref(color),
            "approximation": approximation}
