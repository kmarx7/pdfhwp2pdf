"""HWP 내어쓰기는 첫 줄을 왼쪽 여백에 두고 둘째 줄부터 들인다. Word hanging만 쓰면 첫 줄이 왼쪽 밖으로 나간다."""
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from app.postprocess.hwp_layout import HwpLayoutPostProcessor


def run(indent, left=0, right=0, existing=None):
    shape = {"spacing_top": 0, "spacing_bottom": 0, "line_spacing_type": 0, "line_spacing": 160,
             "indent": indent, "margin_left": left, "margin_right": right}
    data = {"header": {"para_shapes": [shape], "char_shapes": [{"base_size": 1200, "rel_sizes": [100] * 7}]}}
    source = {"para_shape": 0, "header": {"break_type": 0}, "char_shape_runs": [[0, 0]],
              "chars": [{"Text": "생년월일"}], "controls": []}
    target = OxmlElement("w:p")
    if existing:
        properties = target.get_or_add_pPr()
        ind = OxmlElement("w:ind")
        for key, value in existing.items():
            ind.set(qn(f"w:{key}"), value)
        properties.append(ind)
    r = OxmlElement("w:r"); t = OxmlElement("w:t"); t.text = "생년월일"; r.append(t); target.append(r)
    processor = HwpLayoutPostProcessor()
    processor.model = data
    processor.page_breaks = 0
    processor.paragraph(target, source)
    ind = target.find(qn("w:pPr")).find(qn("w:ind"))
    return {} if ind is None else {key.split("}")[1]: value for key, value in ind.attrib.items()}


def test_hanging_indent_keeps_first_line_inside_the_cell():
    # 엔진 결과(hanging만 있고 left=0)를 고쳐 첫 줄이 0, 둘째 줄부터 1055twip 들어가게 한다.
    assert run(-10550, existing={"hanging": "1055"}) == {"left": "1055", "right": "0", "hanging": "1055"}


def test_hanging_indent_adds_to_left_margin():
    assert run(-6540, left=2000, right=2000) == {"left": "854", "right": "200", "hanging": "654"}


def test_first_line_indent_and_plain_margins():
    assert run(1150, left=1000) == {"left": "100", "right": "0", "firstLine": "115"}
    assert run(0, left=1000, right=1000) == {"left": "100", "right": "100"}
