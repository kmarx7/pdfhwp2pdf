"""pdf2docx 0.5.13의 이름 없는 서브셋 글꼴이 전체 글꼴명을 비우는 문제 보완."""
from io import BytesIO

from fontTools.ttLib import TTFont
from pdf2docx.font.Fonts import Font, Fonts


class SafeFonts(Fonts):
    @classmethod
    def extract(cls, document):
        result = []
        for xref in sorted({font[0] for page in document for font in page.get_fonts()}):
            basename, extension, _, data = document.extract_font(xref)
            if not basename:
                continue
            fallback = cls._normalized_font_name(basename)
            family, height = fallback, None
            if extension not in ("n/a", "cff"):
                try:
                    with TTFont(BytesIO(data)) as font:
                        family = cls.get_font_family_name(font) or fallback
                        try:
                            height = cls.get_line_height_factor(font)
                        except (KeyError, ValueError, TypeError):
                            pass
                except Exception:
                    pass
            if family:
                result.append(Font(cls._to_descriptor(fallback), family, height))
        return cls(result)
