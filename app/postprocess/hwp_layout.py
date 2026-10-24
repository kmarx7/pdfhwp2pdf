"""엔진이 생략한 빈 문단·쪽 나눔·줄 간격을 기존 텍스트 개체를 유지해 복원한다."""
import unicodedata

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

from app.domain.errors import DomainError


def compact(text):
    return "".join(unicodedata.normalize("NFC", text).split())


def plain(paragraph):
    values = []
    inline = False
    for char in paragraph["chars"]:
        if "Text" in char and char["Text"]:
            values.append(char["Text"])
            inline = True
        elif char.get("CharCtrl") in (10, 24, 30, 31):
            values.append("-" if char["CharCtrl"] == 24 else " ")
            inline = True
        elif char.get("InlineCtrl", {}).get("code") == 9:
            values.append(" ")
            inline = True
    return "".join(values), inline or any("Picture" in c for c in paragraph["controls"])


class HwpLayoutPostProcessor:
    def process(self, document, model):
        self.model = model
        self.restored_empty = self.page_breaks = 0
        body = document.element.body
        chunks, boundaries, current = [], [], []
        for child in body:
            if child.tag == qn("w:sectPr"):
                continue
            if child.tag == qn("w:p") and child.find(qn("w:pPr")) is not None and child.find(qn("w:pPr")).find(qn("w:sectPr")) is not None:
                chunks.append(current)
                boundaries.append(child)
                current = []
            else:
                current.append(child)
        chunks.append(current)
        if len(chunks) != len(model["sections"]):
            raise DomainError("VALIDATION_FAILED", "본문 구역과 원본 배치 정보를 대응하지 못했습니다.")
        replacement = []
        for index, (source, chunk) in enumerate(zip(model["sections"], chunks)):
            replacement.extend(self.blocks(source["paragraphs"], chunk))
            if index < len(boundaries):
                replacement.append(boundaries[index])
        end = body.find(qn("w:sectPr"))
        for child in list(body):
            if child is not end:
                body.remove(child)
        for index, child in enumerate(replacement):
            body.insert(index, child)
        for section, source in zip(document.sections, model["sections"]):
            page = next((c["SectionDef"].get("page") for p in source["paragraphs"] for c in p["controls"] if "SectionDef" in c), None)
            if page:
                section.top_margin = Pt((page["margin_top"] + page["margin_header"]) / 100)
                section.bottom_margin = Pt((page["margin_bottom"] + page["margin_footer"]) / 100)
        return {"restored_empty_paragraphs": self.restored_empty, "explicit_page_breaks": self.page_breaks}

    def paragraph(self, target, source, anchor=False):
        properties = target.get_or_add_pPr()
        shape = self.model["header"]["para_shapes"][source["para_shape"]]
        spacing = properties.get_or_add_spacing()
        spacing.set(qn("w:before"), str(max(0, round(shape["spacing_top"] / 10))))
        spacing.set(qn("w:after"), str(max(0, round(shape["spacing_bottom"] / 10))))
        kind, value = shape["line_spacing_type"], shape["line_spacing"]
        if anchor:
            spacing.set(qn("w:line"), "1")
            spacing.set(qn("w:lineRule"), "exact")
        elif kind == 0 and value > 0:
            spacing.set(qn("w:line"), str(round(value * 240 / 100)))
            spacing.set(qn("w:lineRule"), "auto")
        if source["header"]["break_type"] & 4:
            properties.get_or_add_pageBreakBefore().set(qn("w:val"), "true")
            self.page_breaks += 1
        if not target.findall(".//" + qn("w:t")) and not anchor:
            runs = source["char_shape_runs"]
            if runs:
                shape_id = runs[-1][1]
                char = self.model["header"]["char_shapes"][shape_id]
                props = OxmlElement("w:rPr")
                properties.append(props)
                size = OxmlElement("w:sz")
                size.set(qn("w:val"), str(max(2, round(char["base_size"] * char["rel_sizes"][0] / 5000))))
                props.append(size)

    def blocks(self, paragraphs, targets):
        result, cursor = [], 0
        for source in paragraphs:
            text, inline = plain(source)
            tables = [control["Table"] for control in source["controls"] if "Table" in control]
            if inline:
                if cursor >= len(targets) or targets[cursor].tag != qn("w:p"):
                    raise DomainError("VALIDATION_FAILED", "원본 문단과 Word 문단의 순서가 다릅니다.")
                target = targets[cursor]
                actual = "".join(node.text or "" for node in target.findall(".//" + qn("w:t")))
                if compact(text) != compact(actual):
                    raise DomainError("VALIDATION_FAILED", "문단의 내용을 안전하게 대응하지 못했습니다.")
                cursor += 1
                self.paragraph(target, source)
                result.append(target)
            elif not tables or source["header"]["break_type"] & 4:
                target = OxmlElement("w:p")
                self.paragraph(target, source, anchor=bool(tables))
                result.append(target)
                self.restored_empty += 1
            for table in tables:
                if cursor >= len(targets) or targets[cursor].tag != qn("w:tbl"):
                    raise DomainError("VALIDATION_FAILED", "원본 표와 Word 표의 순서가 다릅니다.")
                target = targets[cursor]
                cursor += 1
                self.table(target, table)
                result.append(target)
        for extra in targets[cursor:]:
            if extra.tag != qn("w:p") or len(extra):
                raise DomainError("VALIDATION_FAILED", "대응하지 못한 Word 문서 개체가 남았습니다.")
        return result

    def table(self, target, source):
        origins = {(cell["row"], cell["col"]): cell for cell in source["cells"]}
        for row_index, row in enumerate(target.findall(qn("w:tr"))):
            heights = [cell["height"] for cell in source["cells"] if cell["row"] == row_index and cell["row_span"] == 1]
            if heights:
                properties = row.get_or_add_trPr()
                for old in properties.findall(qn("w:trHeight")):
                    properties.remove(old)
                height = OxmlElement("w:trHeight")
                height.set(qn("w:val"), str(max(1, round(max(heights) / 5))))
                height.set(qn("w:hRule"), "atLeast")
                properties.append(height)
            column = 0
            for cell in row.findall(qn("w:tc")):
                original = origins.get((row_index, column))
                span = cell.find(qn("w:tcPr")).find(qn("w:gridSpan"))
                column += int(span.get(qn("w:val"))) if span is not None else 1
                if not original:
                    continue
                blocks = [child for child in cell if child.tag in (qn("w:p"), qn("w:tbl"))]
                restored = self.blocks(original["paragraphs"], blocks)
                for child in blocks:
                    cell.remove(child)
                cell.extend(restored)
                if not restored or restored[-1].tag != qn("w:p"):
                    cell.append(OxmlElement("w:p"))
                properties = cell.find(qn("w:tcPr"))
                for prior in properties.findall(qn("w:vAlign")):
                    properties.remove(prior)
                align = OxmlElement("w:vAlign")
                align.set(qn("w:val"), {0: "top", 1: "center", 2: "bottom"}.get((original["list_attr"] >> 5) & 3, "top"))
                properties.append(align)
