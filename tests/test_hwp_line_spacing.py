"""HWP 퍼센트 줄 간격은 글자 크기 기준이다. Word의 '배수'(글꼴 줄 높이 기준)로 옮기면 줄이 커진다."""
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from app.postprocess.hwp_layout import HwpLayoutPostProcessor


def model(line_spacing=160, sizes=(1200,)):
    return {"header": {
        "para_shapes": [{"spacing_top": 0, "spacing_bottom": 0, "line_spacing_type": 0, "line_spacing": line_spacing}],
        "char_shapes": [{"base_size": size, "rel_sizes": [100] * 7} for size in sizes],
    }}


def source(runs=((0, 0),), controls=()):
    return {"para_shape": 0, "header": {"break_type": 0}, "char_shape_runs": [list(run) for run in runs],
            "chars": [{"Text": "본문"}], "controls": list(controls)}


def paragraph_with_text():
    paragraph = OxmlElement("w:p")
    run = OxmlElement("w:r")
    text = OxmlElement("w:t")
    text.text = "본문"
    run.append(text)
    paragraph.append(run)
    return paragraph


def spacing(target):
    element = target.find(qn("w:pPr")).find(qn("w:spacing"))
    return element.get(qn("w:line")), element.get(qn("w:lineRule"))


def apply(target, data, src):
    processor = HwpLayoutPostProcessor()
    processor.model = data
    processor.page_breaks = 0
    processor.paragraph(target, src)
    return spacing(target)


def test_percent_line_spacing_uses_font_size_in_points():
    # 12pt × 160% = 19.2pt = 384 twips, Word 글꼴 줄 높이를 곱하지 않는다.
    assert apply(paragraph_with_text(), model(160, (1200,)), source()) == ("384", "exact")


def test_largest_font_in_paragraph_sets_line_height():
    data = model(130, (1100, 1600))
    # 16pt × 130% = 20.8pt = 416 twips
    assert apply(paragraph_with_text(), data, source(runs=((0, 0), (2, 1)))) == ("416", "exact")


def test_paragraph_with_picture_is_never_clipped():
    target = paragraph_with_text()
    line, rule = apply(target, model(160, (1000,)), source(controls=({"Picture": {}},)))
    assert (line, rule) == ("320", "atLeast")


def test_empty_restored_paragraph_uses_its_own_char_size():
    target = OxmlElement("w:p")
    assert apply(target, model(200, (1000,)), source()) == ("400", "exact")
