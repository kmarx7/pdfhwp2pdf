"""검증용 합성 HWP 5를 생성한다. 실제 실무 문서 품질의 증거는 아니다."""
import argparse
import copy
import json
from pathlib import Path
import shutil
import struct
import sys
import tempfile

import olefile
import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.engines.hwp.cli import HwpCli


def paragraph(text, **kwargs):
    return {"type": "paragraph", "runs": [{"type": "text", "text": text}], **kwargs}


def cell(text, **kwargs):
    return {"blocks": [paragraph(text)], **kwargs}


def add_page_number(model: dict, section: int = 0, position: int = 5, number_format: int = 0,
                    prefix: int = 0, suffix: int = 0, side: int = 45) -> None:
    """테스트 입력 authoring. 앱의 DOCX 후처리와 별개인 실제 HWP 컨트롤을 넣는다."""
    para = model["sections"][section]["paragraphs"][0]
    index = len(para["controls"])
    para["controls"].append({"Generic": {
        "ctrl_id": list(b"pgnp"), "data": struct.pack("<I4H", (position << 8) | number_format, 0, prefix, suffix, side).hex(),
        "paragraph_lists": [], "extras": [],
    }})
    para["chars"].insert(0, {"ExtCtrl": {"code": 21, "ctrl_id": list(b"pgnp"), "ctrl_index": index,
                                        "payload": (b"pgnp"[::-1] + bytes(8)).hex()}})
    para["header"]["ctrl_mask"] |= 1 << 21
    para["header"]["hwp5_child_order"].append("Control")


def make_test_hwps(folder: Path) -> dict[str, Path]:
    folder = folder.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    cli = HwpCli()
    if not cli.available():
        raise RuntimeError("먼저 .venv/bin/python scripts/install_hwp_engine.py 를 실행하세요.")
    base = {"version": "1.0", "page": {"width_mm": 210, "height_mm": 297, "margin_left_mm": 20,
                                        "margin_right_mm": 20, "margin_top_mm": 18, "margin_bottom_mm": 18},
            "styles": {"title": {"font_family": "Arial", "font_size_pt": 18, "bold": True, "color": "#112233"}},
            "sections": [{"blocks": [paragraph("한글 HWP 변환 12345", style="title"),
                                      paragraph("본문을 Word에서 편집합니다. Editable text.")]}]}
    specs = {"text": copy.deepcopy(base)}
    table = {"type": "table", "width_mm": 150, "columns": [{"width_mm": 40}, {"width_mm": 110}],
             "rows": [{"cells": [cell(a), cell(b)]} for a, b in [("품목", "금액"), ("사과", "100"), ("배", "200")]]}
    specs["table"] = copy.deepcopy(base)
    specs["table"]["sections"][0]["blocks"].append(table)
    specs["merged"] = copy.deepcopy(base)
    specs["merged"]["sections"][0]["blocks"].append({"type": "table", "width_mm": 150,
        "columns": [{"width_mm": 50}, {"width_mm": 50}, {"width_mm": 50}],
        "rows": [{"cells": [cell("세로 병합", row_span=2), cell("가로 병합", col_span=2)]},
                 {"cells": [cell("둘째 행"), cell("오른쪽")]}]})
    specs["image"] = copy.deepcopy(base)
    specs["image"]["sections"][0]["blocks"].append({"type": "image", "path": "image.png", "width_mm": 30, "placement": "inline"})
    specs["sections"] = copy.deepcopy(base)
    specs["sections"]["sections"].append({"blocks": [paragraph("두 번째 섹션의 본문 67890")]})
    specs["header"] = copy.deepcopy(base)
    specs["header"]["sections"][0]["header"] = {"default": [paragraph("머리말 내용") ]}
    results = {}
    with tempfile.TemporaryDirectory(dir=folder, prefix="build-") as temporary:
        work = Path(temporary)
        image = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 30), False)
        image.clear_with(160)
        image.save(work / "image.png")
        for name, spec in specs.items():
            target = folder / f"{name}.hwp"
            if target.exists():
                raise FileExistsError(f"Fixture already exists: {target.name}")
            source = work / f"{name}.json"
            intermediate = work / f"{name}.hwpx"
            source.write_text(json.dumps(spec, ensure_ascii=False))
            cli.run(["compose", str(source), "-o", str(intermediate)], work)
            cli.run(["convert", str(intermediate), "-o", str(target), "--strict"], work)
            results[name] = target
        # 기본 명세가 셀 배경 속성을 제공하지 않아, 테스트 authoring IR에서
        # 단색 배경을 지정한 실제 HWP를 별도로 만든다. 앱 변환 경로와는 무관하다.
        colored = folder / "colored.hwp"
        if colored.exists():
            raise FileExistsError(f"Fixture already exists: {colored.name}")
        model_path = work / "colored-model.json"
        cli.run(["convert", str(results["table"]), "-o", str(model_path), "--embed-bin"], work)
        model = json.loads(model_path.read_text())
        source_table = next(control["Table"] for section in model["sections"] for para in section["paragraphs"]
                            for control in para["controls"] if "Table" in control)
        fill = model["header"]["border_fills"][source_table["cells"][0]["border_fill"] - 1]
        fill.update(fill_type=1, bg_color=0xCCFFFF)
        model_path.write_text(json.dumps(model, ensure_ascii=False))
        cli.run(["new", "--from", str(model_path), "-o", str(colored)], work)
        results["colored"] = colored
        decorated = folder / "decorated.hwp"
        if decorated.exists():
            raise FileExistsError(f"Fixture already exists: {decorated.name}")
        fill.update(fill_type=4, bg_color=None,
                    gradient={"angle_deg": 0.0, "center_x": 50, "center_y": 50, "radial": False,
                              "step": 50, "stops": [[0.0, 0xFFFFFF], [1.0, 0xF7E6DF]]},
                    tail=(struct.pack("<B5i2I", 1, 0, 50, 50, 50, 2, 0xFFFFFF, 0xF7E6DF) + bytes.fromhex("010000003200")).hex())
        fill["sides"][0]["line_type"] = 3
        fill["sides"][2]["line_type"] = 8
        model_path.write_text(json.dumps(model, ensure_ascii=False))
        cli.run(["new", "--from", str(model_path), "-o", str(decorated)], work)
        results["decorated"] = decorated
        for name, source_name in (("page_numbers", "text"), ("roman_numbers", "text"),
                                  ("section_numbers", "sections"), ("inherited_numbers", "sections")):
            target = folder / f"{name}.hwp"
            if target.exists():
                raise FileExistsError(f"Fixture already exists: {target.name}")
            model_path = work / f"{name}-model.json"
            cli.run(["convert", str(results[source_name]), "-o", str(model_path), "--embed-bin"], work)
            model = json.loads(model_path.read_text())
            if name == "roman_numbers":
                add_page_number(model, position=3, number_format=2, prefix=40, suffix=41, side=0)
                model["header"]["properties"]["start_numbers"][0] = 4
            else:
                add_page_number(model)
            if name == "section_numbers":
                add_page_number(model, section=1, position=0, side=0)
            model_path.write_text(json.dumps(model, ensure_ascii=False))
            cli.run(["new", "--from", str(model_path), "-o", str(target)], work)
            results[name] = target
    for name, flag in (("password_flag", 2), ("distribution", 4), ("drm", 16)):
        target = folder / f"{name}.hwp"
        if target.exists():
            raise FileExistsError(f"Fixture already exists: {target.name}")
        shutil.copyfile(results["text"], target)
        with olefile.OleFileIO(target, write_mode=True) as package:
            header = bytearray(package.openstream("FileHeader").read())
            flags = struct.unpack_from("<I", header, 36)[0]
            struct.pack_into("<I", header, 36, flags | flag)
            package.write_stream("FileHeader", bytes(header))
        results[name] = target
    # 플래그 fixture는 실제 암호 알고리즘을 적용한 문서가 아니라 거부 경로 검사용이다.
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("runtime/hwp-samples"))
    arguments = parser.parse_args()
    paths = make_test_hwps(arguments.output_dir)
    print(f"합성 HWP {len(paths)}개 생성: {arguments.output_dir}")
