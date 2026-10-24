import base64
import hashlib
import json
from pathlib import Path
import struct
import zlib

import olefile

from app.domain.errors import DomainError
from app.domain.models import DocumentAnalysis
from app.engines.hwp.cli import HwpCli
from app.services.hwp_page_numbers import parse_page_number, unsupported_page_number
from app.postprocess.hwp_fills import resolve_fill

OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
MAX_STREAM = 20 * 1024 * 1024
MAX_TOTAL = 200 * 1024 * 1024
MAX_IR = 64 * 1024 * 1024
FEATURE_LABELS = {
    "pgnp": "쪽 번호 위치 설정", "head": "머리말", "foot": "꼬리말",
    "cold": "다단 설정", "eqed": "수식", "gso": "도형",
    "fn": "각주", "en": "미주", "atno": "자동 번호", "nwno": "새 번호 지정",
    "pgct": "쪽 번호 제어", "pghd": "쪽 감추기",
    "opaque_paragraph_record": "해석되지 않은 문단 속성",
    "opaque_section_record": "해석되지 않은 구역 속성",
    "unreferenced_control": "연결되지 않은 문서 개체",
    "unresolved_control": "참조를 확인할 수 없는 문서 개체",
}


def guard_hwp_container(source: Path) -> None:
    """실제 HWP5 식별·보호 플래그·파서에 넘기기 전 압축 크기 제한."""
    try:
        with source.open("rb") as stream:
            magic = stream.read(32)
        if magic.startswith(b"HWP Document File V3"):
            raise DomainError("UNSUPPORTED_VARIANT", "HWP 3.x 문서는 지원하지 않습니다.", 415)
        if not magic.startswith(OLE_MAGIC):
            raise DomainError("INVALID_DOCUMENT", "HWP 5 파일의 컨테이너를 확인할 수 없습니다.", 400)
        with olefile.OleFileIO(source) as package:
            paths = package.listdir()
            if len(paths) > 2000:
                raise DomainError("ARCHIVE_LIMIT_EXCEEDED", "HWP 내부 항목 수가 제한을 초과했습니다.", 400)
            if not package.exists("FileHeader"):
                raise DomainError("FORMAT_MISMATCH", "OLE 파일이지만 HWP 문서는 아닙니다.", 400)
            header = package.openstream("FileHeader").read(257)
            if len(header) != 256 or not header.startswith(b"HWP Document File\x00"):
                raise DomainError("INVALID_DOCUMENT", "HWP 문서 헤더가 올바르지 않습니다.", 400)
            if header[35] != 5:
                raise DomainError("UNSUPPORTED_VARIANT", "HWP 5 형식만 지원합니다.", 415)
            flags = struct.unpack_from("<I", header, 36)[0]
            if flags & 2:
                raise DomainError("PASSWORD_PROTECTED", "암호화된 HWP는 변환할 수 없습니다.",
                                  suggestion="원본 작성 도구에서 보호를 해제한 복사본을 준비하세요.")
            if flags & ((1 << 2) | (1 << 4) | (1 << 8) | (1 << 9)):
                raise DomainError("RESTRICTED_DOCUMENT", "배포용 또는 보안 설정이 있는 HWP는 지원하지 않습니다.")
            if not package.exists("DocInfo") or not any(p[0] == "BodyText" for p in paths):
                raise DomainError("INVALID_DOCUMENT", "HWP 본문 구조가 없습니다.", 400)
            total = 0
            for path in paths:
                size = package.get_size(path)
                if size > MAX_STREAM:
                    raise DomainError("ARCHIVE_LIMIT_EXCEEDED", "HWP 내부 스트림이 크기 제한을 초과했습니다.", 400)
                total += size
                if total > MAX_TOTAL:
                    raise DomainError("ARCHIVE_LIMIT_EXCEEDED", "HWP 내부 데이터가 크기 제한을 초과했습니다.", 400)
                if flags & 1 and (path[0] in {"DocInfo", "BodyText", "BinData"}):
                    data = package.openstream(path).read()
                    decoder = zlib.decompressobj(-15)
                    try:
                        expanded = decoder.decompress(data, MAX_STREAM + 1)
                    except zlib.error as exc:
                        # BinData는 항목별로 비압축 저장될 수도 있다. 본문/DocInfo만 필수 deflate다.
                        if path[0] == "BinData":
                            continue
                        raise DomainError("INVALID_DOCUMENT", "HWP 본문 압축 데이터를 읽지 못했습니다.", 400) from exc
                    if len(expanded) > MAX_STREAM or decoder.unconsumed_tail:
                        raise DomainError("ARCHIVE_LIMIT_EXCEEDED", "HWP 압축 해제 크기가 제한을 초과했습니다.", 400)
                    if path[0] != "BinData" and not decoder.eof:
                        raise DomainError("INVALID_DOCUMENT", "HWP 압축 데이터가 잘렸습니다.", 400)
                    total += len(expanded)
                    if total > MAX_TOTAL:
                        raise DomainError("ARCHIVE_LIMIT_EXCEEDED", "HWP 압축 해제 총량이 제한을 초과했습니다.", 400)
    except DomainError:
        raise
    except (OSError, ValueError, IOError, struct.error) as exc:
        raise DomainError("INVALID_DOCUMENT", "HWP 문서 구조를 읽지 못했습니다.", 400) from exc


class HwpAnalyzer:
    def analyze(self, source: Path, workspace: Path, emit=None) -> DocumentAnalysis:
        guard_hwp_container(source)
        intermediate = workspace / "source-model.json"
        HwpCli(emit=emit).run(["convert", str(source), "-o", str(intermediate), "--to", "json", "--embed-bin"], workspace)
        if not intermediate.is_file() or intermediate.stat().st_size > MAX_IR:
            raise DomainError("RESOURCE_LIMIT", "HWP 분석 결과가 처리 크기 제한을 초과했습니다.")
        try:
            model = json.loads(intermediate.read_text())
            return self.inspect_model(model)
        except DomainError:
            raise
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            raise DomainError("INVALID_DOCUMENT", "HWP 분석 결과의 구조가 올바르지 않습니다.", 400) from exc

    def inspect_model(self, model: dict) -> DocumentAnalysis:
        texts, tables, pictures, unsupported, sizes = [], [], [], set(), []
        paragraphs = 0
        page_numbers = []
        placement = None
        section_has_text = False
        warnings = ["HWP 변환은 실험 기능입니다. 실제 Word 화면과 복잡한 실무 문서 품질은 미검증입니다.",
                    "원본 글꼴 이름·크기와 기본 문단/표를 옮기며 페이지 배치·장식·자동 번호의 동일함은 보장하지 않습니다.",
                    "이미지는 인라인으로 배치하며 회전·자르기 효과는 보존되지 않을 수 있습니다. Word에 원본 글꼴이 없으면 대체됩니다."]

        def walk(items: list, depth: int = 0):
            nonlocal paragraphs, placement, section_has_text
            if depth > 32:
                raise DomainError("RESOURCE_LIMIT", "HWP 표 중첩 깊이가 제한을 초과했습니다.")
            for paragraph in items:
                if paragraph.get("extras"):
                    unsupported.add("opaque_paragraph_record")
                paragraphs += 1
                if paragraphs > 20000:
                    raise DomainError("RESOURCE_LIMIT", "HWP 문단 수가 처리 제한을 초과했습니다.")
                text = []
                references = set()
                for char in paragraph["chars"]:
                    if "Text" in char:
                        text.append(char["Text"])
                    elif "CharCtrl" in char:
                        code = char["CharCtrl"]
                        if code == 24:
                            text.append("-")
                        elif code in (10, 13, 30, 31):
                            text.append(" ")
                        elif code not in (0,):
                            unsupported.add(f"character_control_{code}")
                    elif "InlineCtrl" in char:
                        code = char["InlineCtrl"]["code"]
                        if code not in (9, 4):
                            unsupported.add(f"inline_control_{code}")
                    elif "ExtCtrl" in char:
                        reference = char["ExtCtrl"].get("ctrl_index")
                        if reference is None:
                            unsupported.add("unresolved_control")
                        else:
                            references.add(reference)
                    else:
                        unsupported.add("unknown_character")
                texts.append("".join(text))
                for index, control in enumerate(paragraph["controls"]):
                    if index not in references:
                        unsupported.add("unreferenced_control")
                    if "SectionDef" in control:
                        page = control["SectionDef"].get("page")
                        if page:
                            sizes.append((page["width"] / 100, page["height"] / 100))
                    elif "Table" in control:
                        table = control["Table"]
                        if not 0 < table["rows"] <= 1000 or not 0 < table["cols"] <= 100:
                            raise DomainError("RESOURCE_LIMIT", "HWP 표의 행·열 수가 제한을 초과했습니다.")
                        occupied = set()
                        for cell in table["cells"]:
                            row, column = cell["row"], cell["col"]
                            end_row, end_column = row + cell["row_span"], column + cell["col_span"]
                            if not (0 <= row < end_row <= table["rows"] and 0 <= column < end_column <= table["cols"]):
                                raise DomainError("INVALID_DOCUMENT", "HWP 표의 셀 범위가 올바르지 않습니다.", 400)
                            for y in range(row, end_row):
                                for x in range(column, end_column):
                                    if (y, x) in occupied:
                                        raise DomainError("INVALID_DOCUMENT", "HWP 표에 겹치는 셀이 있습니다.", 400)
                                    occupied.add((y, x))
                        tables.append({"rows": table["rows"], "cols": table["cols"], "cells": [
                            {key: cell[key] for key in ("row", "col", "row_span", "col_span", "width", "border_fill", "margins")}
                            for cell in table["cells"]]})
                        for cell in table["cells"]:
                            walk(cell["paragraphs"], depth + 1)
                    elif "Picture" in control:
                        pictures.append(control["Picture"])
                    elif "Generic" in control:
                        generic = control["Generic"]
                        name = bytes(generic["ctrl_id"]).decode("latin1").strip()
                        if name == "cold" and (generic.get("column_def") or {}).get("count") == 1:
                            pass
                        elif name == "bokm" and not generic.get("paragraph_lists"):
                            warnings.append("책갈피 링크 위치는 보존하지 않습니다.")
                        elif name == "pgnp":
                            candidate = parse_page_number(generic)
                            if depth or (section_has_text and candidate != placement):
                                raise unsupported_page_number("표 안 또는 구역 본문 중간에서 번호 설정이 바뀝니다.")
                            placement = candidate
                        else:
                            # 머리말·꼬리말·필드·도형·수식·각주는 조용히 누락시키지 않는다.
                            unsupported.add(name or "unknown_control")
                    else:
                        unsupported.add("unknown_control")
                if any(value.strip() for value in text) or paragraph["controls"] and any(
                    "Table" in control or "Picture" in control for control in paragraph["controls"]
                ):
                    section_has_text = True

        sections = model["sections"]
        if not sections or len(sections) > 100:
            raise DomainError("RESOURCE_LIMIT", "HWP 섹션 수가 지원 범위를 벗어났습니다.")
        for section in sections:
            section_has_text = False
            if section.get("extras"):
                unsupported.add("opaque_section_record")
            walk(section["paragraphs"])
            page_numbers.append(placement.copy() if placement else None)
        if unsupported:
            features = sorted(unsupported)
            labels = [FEATURE_LABELS.get(feature, "미지원 문서 요소") for feature in features]
            summary = " · ".join(dict.fromkeys(labels))
            raise DomainError("UNSUPPORTED_FEATURE", "현재 보존할 수 없는 HWP 요소가 포함되어 변환을 중단했습니다.",
                              details={"features": features, "feature_labels": labels},
                              suggestion=f"감지된 미지원 요소: {summary}. 이 요소를 보존하는 변환은 아직 지원하지 않습니다. 같은 파일을 다시 시도해도 해결되지 않습니다.")
        if not any(text.strip() for text in texts):
            raise DomainError("NO_EDITABLE_TEXT", "HWP에서 편집 가능한 본문 텍스트를 찾지 못했습니다.")
        image_hashes = self.picture_hashes(model, pictures)
        fills = model["header"]["border_fills"]
        used_fills = {cell["border_fill"] for table in tables for cell in table["cells"]}
        approximated = set()
        for index in used_fills:
            if not 1 <= index <= len(fills):
                raise DomainError("INVALID_DOCUMENT", "HWP 표 배경 참조가 올바르지 않습니다.")
            if resolve_fill(fills[index - 1])["approximation"]:
                approximated.add(index)
        if approximated:
            warnings.append("서식 변경: 표의 두 색상 선형 그라데이션 배경을 중간색의 단색 배경으로 근사했습니다. 그라데이션 효과는 보존되지 않았습니다. 본문·표는 편집 가능하며 원본과 배경을 비교해 주세요.")
        fonts = sorted({font["name"] for group in model["header"]["fonts"] for font in group})
        start_numbers = model["header"].get("properties", {}).get("start_numbers", [1])
        page_start = max(1, int(start_numbers[0]))
        if any(page_numbers):
            warnings.append("쪽 번호는 Word 자동 PAGE 필드입니다. Word에서 필드 업데이트 후 배치와 번호를 확인하세요. 원본과 실제 페이지 나눔은 다를 수 있습니다.")
        return DocumentAnalysis(None, sizes, texts, fonts, len(tables), list(dict.fromkeys(warnings)), "hwp",
                                {"tables": tables, "image_hashes": image_hashes, "sections": len(sections),
                                 "border_fills": model["header"]["border_fills"],
                                 "page_numbers": page_numbers, "page_start": page_start})

    @staticmethod
    def picture_hashes(model: dict, pictures: list[dict]) -> list[str]:
        if not pictures:
            return []
        # 고정 버전의 --embed-bin 출력은 data_b64에 원본 이미지 바이트를 담는다.
        # Picture의 참조 해결은
        # 버전 고정 모델 구조에 맞춰 검사하고 외부 링크 이미지는 거부한다.
        streams = {item["name"]: item["data_b64"] for item in model["bin_streams"]}
        hashes = []
        for picture in pictures:
            reference = picture["bin_ref"]
            if "Id" in reference:
                index = reference["Id"] - 1
                if not 0 <= index < len(model["header"]["bin_data"]):
                    raise DomainError("UNSUPPORTED_FEATURE", "HWP 이미지 참조 인덱스가 잘못되었습니다.")
                item = model["header"]["bin_data"][index]
                storage = item.get("storage_id")
                if storage is None or item.get("link_abs") or item.get("link_rel"):
                    raise DomainError("UNSUPPORTED_FEATURE", "외부 링크 이미지는 지원하지 않습니다.")
                expected_name = f'BIN{storage:04X}.{item.get("extension") or ""}'
                candidates = [data for name, data in streams.items() if name.casefold() == expected_name.casefold()]
            elif "ItemRef" in reference:
                item = reference["ItemRef"]
                candidates = [data for name, data in streams.items() if name == item or name.endswith("/" + item)
                              or Path(name).stem == item]
            else:
                candidates = []
            if len(candidates) != 1:
                raise DomainError("UNSUPPORTED_FEATURE", "HWP 이미지의 내부 참조를 확인할 수 없습니다.")
            data = base64.b64decode(candidates[0], validate=True)
            if not data.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a", b"BM")):
                raise DomainError("UNSUPPORTED_FEATURE", "이 HWP 이미지 형식은 아직 지원하지 않습니다.")
            if picture.get("width", 0) <= 0 or picture.get("height", 0) <= 0:
                raise DomainError("UNSUPPORTED_FEATURE", "HWP 이미지 크기를 확인할 수 없습니다.")
            hashes.append(hashlib.sha256(data).hexdigest())
        return hashes
