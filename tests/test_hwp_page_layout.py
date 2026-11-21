"""Word에서 실제 사용자 HWP가 원본보다 쪽이 밀린 원인 두 가지의 회귀 테스트(2026-11-21).

1) 여러 쪽에 걸친 표 행은 HWP에 합계 높이가 저장된다. 이를 Word 최소 행 높이로 쓰면
   Word가 행 전체를 다음 쪽으로 밀어 이후 모든 쪽이 밀린다.
2) HWP 가로 용지는 세로 치수 + 가로 속성으로 저장된다. Word는 pgSz 너비/높이를 그대로 쓰므로
   값을 바꾸지 않으면 세로 쪽이 되어 넓은 표가 오른쪽 밖으로 넘친다.
"""
from docx import Document
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn

from app.postprocess.hwp_layout import HwpLayoutPostProcessor

A4 = {"width": 59528, "height": 84186, "margin_left": 5669, "margin_right": 5669, "margin_top": 4251,
      "margin_bottom": 4252, "margin_header": 2834, "margin_footer": 2834, "gutter": 0, "attr": 0}


def row_heights(row_hwp_heights, body_height):
    document = Document()
    table = document.add_table(rows=len(row_hwp_heights), cols=1)
    source = {"cells": [{"row": index, "col": 0, "row_span": 1, "col_span": 1, "height": height, "list_attr": 0, "paragraphs": []}
                        for index, height in enumerate(row_hwp_heights)]}
    processor = HwpLayoutPostProcessor()
    processor.model = {"header": {}}
    processor.restored_empty = processor.page_breaks = 0
    processor.body_height = body_height
    processor.table(table._tbl, source)
    result = []
    for row in table._tbl.findall(qn("w:tr")):
        height = row.find(qn("w:trPr")).find(qn("w:trHeight")) if row.find(qn("w:trPr")) is not None else None
        result.append(None if height is None else int(height.get(qn("w:val"))))
    return result


def test_body_height_excludes_margins_header_and_footer():
    assert HwpLayoutPostProcessor.body_height_of(A4) == 84186 - 4251 - 4252 - 2834 - 2834
    assert HwpLayoutPostProcessor.body_height_of({**A4, "attr": 1}) == 59528 - 4251 - 4252 - 2834 - 2834


def test_row_taller_than_a_page_gets_no_minimum_height():
    body = HwpLayoutPostProcessor.body_height_of(A4)
    # 사용자 문서: 안내 상자의 본문 행이 약 2.2쪽(136225 HWPUNIT)에 걸친다.
    assert row_heights([1840, 136225], body) == [368, None]


def test_row_that_fits_on_a_page_keeps_minimum_height():
    body = HwpLayoutPostProcessor.body_height_of(A4)
    assert row_heights([1840, body], body) == [368, round(body / 5)]


def test_landscape_hwp_section_becomes_landscape_word_page():
    section = Document().sections[0]
    HwpLayoutPostProcessor.apply_page(section, {**A4, "attr": 1})
    assert section.orientation == WD_ORIENT.LANDSCAPE
    assert section.page_width > section.page_height
    assert round(section.page_width.pt) == round(84186 / 100)


def test_portrait_hwp_section_stays_portrait():
    section = Document().sections[0]
    HwpLayoutPostProcessor.apply_page(section, A4)
    assert section.orientation == WD_ORIENT.PORTRAIT
    assert section.page_height > section.page_width


def test_analyzer_records_landscape_section_as_wide_page():
    from app.services.hwp_analyzer import HwpAnalyzer
    model = {"header": {"border_fills": [], "fonts": [[]], "bin_data": []}, "bin_streams": [],
             "sections": [{"paragraphs": [{"chars": [{"Text": "본문"}, {"ExtCtrl": {"ctrl_index": 0}}],
                                           "controls": [{"SectionDef": {"page": {**A4, "attr": 1}}}]}]}]}
    width, height = HwpAnalyzer().inspect_model(model).page_sizes[0]
    assert (round(width), round(height)) == (round(84186 / 100), round(59528 / 100))


def para(v_pos, text="", controls=(), page_break=False):
    chars = [{"Text": ch} for ch in text]
    return {"chars": chars, "controls": list(controls), "line_segs": [{"v_pos": v_pos}],
            "header": {"break_type": 4 if page_break else 0}}


def test_page_start_after_empty_filler_is_detected():
    # 본문 → 빈 줄 2개(앞 쪽 아래) → 한글에서 새 쪽 시작(v_pos 감소) → 표지 빈 줄
    paragraphs = [para(0, "본문"), para(60000), para(62400), para(0), para(2400)]
    assert HwpLayoutPostProcessor.filler_page_starts(paragraphs) == ({3}, {1, 2})


def test_existing_page_break_and_text_flow_are_left_alone():
    # 이미 쪽 나누기가 있거나, 앞 문단이 글자 문단(쪽을 넘겨 이어질 수 있음)이면 강제하지 않는다.
    assert HwpLayoutPostProcessor.filler_page_starts([para(0), para(60000), para(0, page_break=True)]) == (set(), set())
    assert HwpLayoutPostProcessor.filler_page_starts([para(0, "본문"), para(60000, "긴 문단"), para(0)]) == (set(), set())


def test_page_start_paragraph_breaks_page_and_filler_collapses():
    from docx.oxml import OxmlElement
    processor = HwpLayoutPostProcessor()
    processor.model = {"header": {"para_shapes": [{"spacing_top": 0, "spacing_bottom": 0, "line_spacing_type": 0,
                                                   "line_spacing": 160, "indent": 0, "margin_left": 0, "margin_right": 0}],
                                  "char_shapes": [{"base_size": 1500, "rel_sizes": [100] * 7}]}}
    processor.page_breaks = 0
    source = {"para_shape": 0, "header": {"break_type": 0}, "char_shape_runs": [[0, 0]], "chars": [], "controls": []}
    start, filler = OxmlElement("w:p"), OxmlElement("w:p")
    processor.paragraph(start, source, page_start=True)
    processor.paragraph(filler, source, filler=True)
    assert start.find(qn("w:pPr")).find(qn("w:pageBreakBefore")) is not None
    assert processor.page_breaks == 1
    spacing = filler.find(qn("w:pPr")).find(qn("w:spacing"))
    assert (spacing.get(qn("w:line")), spacing.get(qn("w:lineRule"))) == ("1", "exact")


def test_word_auto_spacing_between_hangul_and_digits_is_disabled():
    """한글은 '2026년' 사이에 간격을 넣지 않는다. Word 기본값은 넣어 제목 줄이 넘친다."""
    document = Document()
    HwpLayoutPostProcessor.disable_east_asian_autospace(document)
    defaults = document.styles.element.find(qn("w:docDefaults")).find(qn("w:pPrDefault")).find(qn("w:pPr"))
    for name in ("w:autoSpaceDE", "w:autoSpaceDN"):
        assert defaults.find(qn(name)).get(qn("w:val")) == "0"
    HwpLayoutPostProcessor.disable_east_asian_autospace(document)  # 두 번 적용해도 중복되지 않는다.
    assert len(defaults.findall(qn("w:autoSpaceDE"))) == 1


def test_adjacent_tables_from_separate_paragraphs_stay_separate_in_word():
    """Word는 사이에 문단이 없는 두 표를 하나로 합친다(붙임1 표 너비가 위 표에 맞춰 줄어든 원인)."""
    document = Document()
    first, second = document.add_table(rows=1, cols=1), document.add_table(rows=1, cols=1)
    targets = [first._tbl, second._tbl]

    def table_paragraph():
        cell = {"row": 0, "col": 0, "row_span": 1, "col_span": 1, "height": 1000, "list_attr": 0, "paragraphs": []}
        return {"para_shape": 0, "header": {"break_type": 0}, "char_shape_runs": [], "chars": [],
                "controls": [{"Table": {"cells": [cell]}}]}

    processor = HwpLayoutPostProcessor()
    processor.model = {"header": {"para_shapes": [{"spacing_top": 0, "spacing_bottom": 0, "line_spacing_type": 0,
                                                   "line_spacing": 160, "indent": 0, "margin_left": 0, "margin_right": 0}],
                                  "char_shapes": []}}
    processor.restored_empty = processor.page_breaks = 0
    result = processor.blocks([table_paragraph(), table_paragraph()], targets)
    assert [element.tag for element in result] == [qn("w:tbl"), qn("w:p"), qn("w:tbl")]
    spacing = result[1].find(qn("w:pPr")).find(qn("w:spacing"))
    assert (spacing.get(qn("w:line")), spacing.get(qn("w:lineRule"))) == ("1", "exact")


def test_document_ending_with_table_gets_zero_height_final_paragraph():
    """Word는 표로 끝나는 문서 뒤에 기본 크기 문단을 덧붙여, 쪽 끝 표 뒤에 빈 쪽을 만든다."""
    document = Document()
    body = document.element.body
    for child in [c for c in body if c.tag != qn("w:sectPr")]:
        body.remove(child)
    table = document.add_table(rows=1, cols=1)
    cell = {"row": 0, "col": 0, "row_span": 1, "col_span": 1, "height": 1000, "list_attr": 0, "paragraphs": []}
    model = {"header": {"para_shapes": [{"spacing_top": 0, "spacing_bottom": 0, "line_spacing_type": 0,
                                         "line_spacing": 160, "indent": 0, "margin_left": 0, "margin_right": 0}],
                        "char_shapes": []},
             "sections": [{"paragraphs": [{"para_shape": 0, "header": {"break_type": 0}, "char_shape_runs": [],
                                           "chars": [], "controls": [{"Table": {"cells": [cell]}}]}]}]}
    HwpLayoutPostProcessor().process(document, model)
    blocks = [c for c in body if c.tag != qn("w:sectPr")]
    assert [c.tag for c in blocks] == [qn("w:tbl"), qn("w:p")]
    spacing = blocks[-1].find(qn("w:pPr")).find(qn("w:spacing"))
    assert (spacing.get(qn("w:line")), spacing.get(qn("w:lineRule"))) == ("1", "exact")
