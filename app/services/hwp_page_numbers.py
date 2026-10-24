"""고정 hwp-cli IR의 pgnp 12바이트를 제한된 Word 페이지 번호 설정으로 해석한다."""
import struct

from app.domain.errors import DomainError


NUMBER_FORMATS = {
    0: ("decimal", "ARABIC"), 2: ("upperRoman", "ROMAN"),
    3: ("lowerRoman", "roman"), 4: ("upperLetter", "ALPHABETIC"),
    5: ("lowerLetter", "alphabetic"),
}


def unsupported_page_number(reason: str) -> DomainError:
    return DomainError(
        "UNSUPPORTED_FEATURE", f"쪽 번호 설정을 보존할 수 없어 중단했습니다: {reason}",
        details={"features": ["pgnp"], "feature_labels": ["쪽 번호 위치 설정"], "reason": reason},
        suggestion="현재 구역 시작의 위·아래 왼쪽/가운데/오른쪽 번호만 지원합니다. 원본은 변경하지 않았습니다.",
    )


def parse_page_number(control: dict) -> dict:
    try:
        data = bytes.fromhex(control["data"])
    except (KeyError, TypeError, ValueError) as exc:
        raise unsupported_page_number("쪽 번호 데이터 형식을 확인할 수 없습니다.") from exc
    if len(data) != 12 or any(control.get(name) for name in ("paragraph_lists", "extras", "raw_children")):
        raise unsupported_page_number("알 수 없는 쪽 번호 데이터가 포함되어 있습니다.")
    props, user, prefix, suffix, side = struct.unpack("<I4H", data)
    position, number_format = (props >> 8) & 15, props & 255
    if props >> 12 or position > 6:
        raise unsupported_page_number("안쪽·바깥쪽 교대 배치 또는 알 수 없는 위치입니다.")
    if number_format not in NUMBER_FORMATS or user:
        raise unsupported_page_number("지원하지 않는 숫자 모양 또는 사용자 지정 문자입니다.")

    def char(value):
        if value == 0:
            return ""
        if value < 32 or 0xD800 <= value <= 0xDFFF or value in (0xFFFE, 0xFFFF):
            raise unsupported_page_number("지원하지 않는 장식 문자입니다.")
        return chr(value)

    side_text = char(side)
    return {"position": position, "format": NUMBER_FORMATS[number_format][0],
            "field_format": NUMBER_FORMATS[number_format][1],
            "prefix": (side_text + " " if side_text else "") + char(prefix),
            "suffix": char(suffix) + (" " + side_text if side_text else "")}
