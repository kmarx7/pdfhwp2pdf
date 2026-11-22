"""HWP 칸의 남는 빈 공간은 Word에서 지울 수 있는 빈 줄이어야 한다(2026-11-23 사용자 보고).

사용자 문서의 '작성 요령' 바깥 칸은 HWP 높이가 한 쪽(66921 HWPUNIT)이고 안쪽 안내 상자는
그 절반 정도다. 이 높이를 Word 최소 행 높이로 쓰면 안내 상자를 지우거나 글을 줄여도 칸이
줄지 않아 빈 공간을 없앨 수 없다. 남는 공간은 최소 높이 대신 선택·삭제 가능한 빈 문단으로 둔다.
"""
from docx import Document
from docx.oxml.ns import qn

from app.postprocess.hwp_layout import HwpLayoutPostProcessor

# 내용 문단은 300%(10pt → 600 twips)로 두어 빈 줄(약 320 twips)과 구별한다.
SHAPES = {"para_shapes": [{"spacing_top": 0, "spacing_bottom": 0, "line_spacing_type": 0, "line_spacing": 300,
                           "indent": 0, "margin_left": 0, "margin_right": 0}],
          "char_shapes": [{"base_size": 1000, "rel_sizes": [100] * 7}]}


def empty_paragraph(line_height):
    return {"para_shape": 0, "header": {"break_type": 0}, "char_shape_runs": [[0, 0]], "chars": [], "controls": [],
            "line_segs": [{"v_pos": 0, "line_height": line_height}]}


def cell(height, content, valign=0, margins=(0, 0, 0, 0)):
    return {"row": 0, "col": 0, "row_span": 1, "col_span": 1, "height": height, "list_attr": valign << 5,
            "margins": list(margins), "paragraphs": [empty_paragraph(content)]}


def convert(source_cell, body_height=200000):
    document = Document()
    table = document.add_table(rows=1, cols=1)
    processor = HwpLayoutPostProcessor()
    processor.model = {"header": SHAPES}
    processor.restored_empty = processor.page_breaks = 0
    processor.body_height = body_height
    processor.table(table._tbl, {"cells": [source_cell]})
    row = table._tbl.find(qn("w:tr"))
    height = row.find(qn("w:trPr")).find(qn("w:trHeight"))
    tc = row.find(qn("w:tc"))
    paragraphs = tc.findall(qn("w:p"))
    return height, paragraphs


def line_twips(paragraph):
    spacing = paragraph.find(qn("w:pPr")).find(qn("w:spacing"))
    return int(spacing.get(qn("w:line"))), spacing.get(qn("w:lineRule"))


def test_large_blank_space_becomes_deletable_empty_lines_not_minimum_height():
    # 66921 높이 칸에 내용 34495 + 위아래 여백 141씩: 남는 공간 32144 HWPUNIT ≈ 6429 twips
    height, paragraphs = convert(cell(66921, 34495, margins=(510, 510, 141, 141)))
    assert height is None
    fillers = paragraphs[1:]
    assert len(fillers) >= 10
    total = sum(line_twips(p)[0] for p in fillers)
    # Word가 내용을 조금 더 높게 그려 쪽이 넘치지 않도록 빈 공간의 70%만 되살린다.
    assert abs(total - round((66921 - 34495 - 282) / 5 * 0.7)) <= len(fillers)
    # 글자 크기가 큰 칸(표지 제목)에서도 원래 공간만큼만 차지하도록 고정 높이로 둔다.
    assert {line_twips(p)[1] for p in fillers} == {"exact"}
    assert all(line_twips(p)[0] < 600 for p in fillers)
    assert all(not p.findall(".//" + qn("w:t")) for p in fillers)


def test_center_aligned_cell_splits_blank_lines_above_and_below_content():
    _, paragraphs = convert(cell(66921, 34495, valign=1))
    content = [index for index, p in enumerate(paragraphs) if line_twips(p)[0] == 600]
    assert len(content) == 1
    above, below = content[0], len(paragraphs) - content[0] - 1
    assert above > 0 and below > 0 and abs(above - below) <= 1


def test_bottom_aligned_cell_puts_blank_lines_above_content():
    _, paragraphs = convert(cell(66921, 34495, valign=2))
    assert line_twips(paragraphs[-1])[0] == 600
    assert line_twips(paragraphs[0])[0] < 600


def test_small_slack_keeps_minimum_row_height():
    # 이름 입력 칸처럼 몇 mm 남는 칸은 표 모양을 위해 최소 높이를 유지한다.
    height, paragraphs = convert(cell(4395, 1200, margins=(510, 510, 141, 141)))
    assert int(height.get(qn("w:val"))) == round(4395 / 5)
    assert height.get(qn("w:hRule")) == "atLeast"
    assert len(paragraphs) == 1


def page_box(v_pos=0):
    """한 쪽을 거의 채우는 1칸 표 문단(사용자 문서의 Q1~Q4 작성 칸)."""
    box = cell(66921, 34495, margins=(510, 510, 141, 141))
    return {"para_shape": 0, "header": {"break_type": 0}, "char_shape_runs": [], "chars": [],
            "controls": [{"Table": {"cells": [box]}}], "line_segs": [{"v_pos": v_pos, "line_height": 69252}]}


def test_box_that_filled_a_page_keeps_next_box_on_a_new_page():
    """칸을 줄일 수 있게 하면 다음 표가 같은 쪽으로 올라온다. 한글에서 새 쪽이던 위치에 쪽 나누기를 둔다."""
    document = Document()
    targets = [document.add_table(rows=1, cols=1)._tbl, document.add_table(rows=1, cols=1)._tbl]
    processor = HwpLayoutPostProcessor()
    processor.model = {"header": SHAPES}
    processor.restored_empty = processor.page_breaks = 0
    processor.body_height = 70015
    result = processor.blocks([page_box(), page_box()], targets)
    assert [element.tag for element in result] == [qn("w:tbl"), qn("w:p"), qn("w:tbl")]
    assert result[1].find(qn("w:pPr")).find(qn("w:pageBreakBefore")) is not None
    assert processor.page_breaks == 1


def test_boxes_on_the_same_hwp_page_get_no_page_break():
    document = Document()
    targets = [document.add_table(rows=1, cols=1)._tbl, document.add_table(rows=1, cols=1)._tbl]
    processor = HwpLayoutPostProcessor()
    processor.model = {"header": SHAPES}
    processor.restored_empty = processor.page_breaks = 0
    processor.body_height = 200000
    result = processor.blocks([page_box(0), page_box(69252)], targets)
    assert result[1].find(qn("w:pPr")).find(qn("w:pageBreakBefore")) is None
    assert processor.page_breaks == 0
