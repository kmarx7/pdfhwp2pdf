from io import BytesIO

from fontTools.ttLib import TTFont, newTable

from app.engines.pdf.font_compat import SafeFonts


def test_subset_font_without_family_or_os2_keeps_basename():
    font = TTFont()
    font["name"] = newTable("name")
    font["name"].names = []
    stream = BytesIO()
    font.save(stream)

    class Page:
        def get_fonts(self):
            return [(1,)]

    class PDF:
        def __iter__(self):
            return iter([Page()])

        def extract_font(self, xref):
            return "ABCDEF+FixtureSans-Bold", "ttf", "TrueType", stream.getvalue()

    fonts = SafeFonts.extract(PDF())
    assert fonts.get("FixtureSans-Bold").name == "FixtureSans"
    assert fonts.get("UnrelatedFont") is None  # 빈 descriptor가 모든 글꼴을 잡아먹지 않음
