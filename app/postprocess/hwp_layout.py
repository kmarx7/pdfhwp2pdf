"""엔진이 생략한 빈 문단·쪽 나눔·줄 간격을 기존 텍스트 개체를 유지해 복원한다."""
import unicodedata
from copy import deepcopy

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.section import WD_ORIENT
from docx.shared import Pt

from app.domain.errors import DomainError

# 칸의 빈 공간이 이보다 크면(약 11mm, 두 줄) 최소 행 높이 대신 지울 수 있는 빈 줄로 둔다.
MIN_BLANK_TWIPS = 640
# 빈 줄 하나의 기준 높이(10pt × 160% = 16pt).
BLANK_LINE_TWIPS = 320
# Word는 같은 내용을 한글보다 조금 더 높게 그린다(대체 글꼴·표 테두리). 한 쪽을 거의 채운 칸의 빈 공간을
# 그대로 되살리면 칸이 다음 쪽으로 넘치므로(사용자 문서 12쪽 → 15쪽) 빈 공간의 70%만 빈 줄로 둔다.
BLANK_SPACE_RATIO = 0.7


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
        self.restored_empty = self.page_breaks = self.blank_lines = 0
        self.shrunk_tables = set()
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
            page = self.section_page(source)
            self.body_height = self.body_height_of(page) if page else None
            starts, fillers = self.filler_page_starts(source["paragraphs"])
            self.page_starts = {id(source["paragraphs"][index]) for index in starts}
            self.fillers = {id(source["paragraphs"][index]) for index in fillers}
            replacement.extend(self.blocks(source["paragraphs"], chunk))
            self.page_starts, self.fillers = set(), set()
            if index < len(boundaries):
                replacement.append(boundaries[index])
        if replacement and replacement[-1].tag == qn("w:tbl"):
            # Word는 표로 끝나는 문서 뒤에 기본 크기 문단을 덧붙여 쪽 끝 표 뒤에 빈 쪽을 만든다.
            closing = OxmlElement("w:p")
            spacing = OxmlElement("w:spacing")
            for name, value in (("w:before", "0"), ("w:after", "0"), ("w:line", "1"), ("w:lineRule", "exact")):
                spacing.set(qn(name), value)
            closing.get_or_add_pPr().append(spacing)
            replacement.append(closing)
        end = body.find(qn("w:sectPr"))
        for child in list(body):
            if child is not end:
                body.remove(child)
        for index, child in enumerate(replacement):
            body.insert(index, child)
        for section, source in zip(document.sections, model["sections"]):
            page = self.section_page(source)
            if page:
                self.apply_page(section, page)
        self.disable_east_asian_autospace(document)
        return {"restored_empty_paragraphs": self.restored_empty, "explicit_page_breaks": self.page_breaks,
                "editable_blank_lines": self.blank_lines}

    @staticmethod
    def filler_page_starts(paragraphs):
        """빈 줄로 위치를 맞춘 뒤 한글이 새 쪽을 시작한 문단과, 앞 쪽 아래에 남은 빈 줄을 찾는다.

        빈 문단은 한 줄이라 쪽을 넘겨 이어지지 않으므로, 빈 문단 다음에 v_pos가 줄면 그 문단이
        원본의 쪽 시작임이 확실하다. 글꼴 대체로 Word 내용이 조금만 길어도 빈 줄이 다음 쪽으로
        넘어가 표지가 밀리므로, 쪽 시작을 명시하고 보이지 않는 앞 쪽 빈 줄은 높이를 최소로 둔다.
        """
        def empty(paragraph):
            return not paragraph["controls"] and not any("Text" in char for char in paragraph["chars"])

        starts, fillers = set(), set()
        for index in range(1, len(paragraphs)):
            previous, current = paragraphs[index - 1], paragraphs[index]
            if not (previous.get("line_segs") and current.get("line_segs")) or not empty(previous):
                continue
            if current["header"]["break_type"] & 4 or any("Table" in c for c in current["controls"]):
                continue
            if current["line_segs"][0]["v_pos"] < previous["line_segs"][-1]["v_pos"]:
                starts.add(index)
                back = index - 1
                while back >= 0 and empty(paragraphs[back]) and back not in starts:
                    fillers.add(back)
                    back -= 1
        return starts, fillers

    def paragraph(self, target, source, anchor=False, page_start=None, filler=None):
        if page_start is None:
            page_start = id(source) in getattr(self, "page_starts", ())
        if filler is None:
            filler = id(source) in getattr(self, "fillers", ())
        anchor = anchor or filler
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
            # HWP 퍼센트는 글자 크기 기준이다(12pt × 160% = 19.2pt). Word의 auto 배수는 글꼴 줄 높이
            # (맑은 고딕 1.33배)를 다시 곱해 줄이 약 33% 커지므로 문단의 가장 큰 글자로 pt를 계산한다.
            size = self.largest_font_pt(source)
            if size:
                has_picture = any("Picture" in control for control in source["controls"])
                spacing.set(qn("w:line"), str(round(size * 20 * value / 100)))
                # 그림이 든 문단은 고정 높이로 자르지 않는다.
                spacing.set(qn("w:lineRule"), "atLeast" if has_picture else "exact")
            else:
                spacing.set(qn("w:line"), str(round(value * 240 / 100)))
                spacing.set(qn("w:lineRule"), "auto")
        self.indentation(properties, shape)
        if source["header"]["break_type"] & 4 or page_start:
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

    @staticmethod
    def indentation(properties, shape):
        """HWP 문단 여백·들여쓰기를 Word 단위(엔진과 같은 1/10 비율)로 다시 쓴다.

        HWP 내어쓰기(음수)는 첫 줄을 왼쪽 여백에 두고 둘째 줄부터 들인다. Word hanging은
        첫 줄을 left - hanging에 두므로 left에 내어쓰기 폭을 더해야 첫 줄이 표 칸 밖으로 나가지 않는다.
        """
        if "indent" not in shape:
            return
        left = round(shape.get("margin_left", 0) / 10)
        right = round(shape.get("margin_right", 0) / 10)
        indent = round(shape["indent"] / 10)
        for old in properties.findall(qn("w:ind")):
            properties.remove(old)
        if not (left or right or indent):
            return
        ind = OxmlElement("w:ind")
        if indent < 0:
            ind.set(qn("w:left"), str(left - indent))
            ind.set(qn("w:right"), str(right))
            ind.set(qn("w:hanging"), str(-indent))
        else:
            ind.set(qn("w:left"), str(left))
            ind.set(qn("w:right"), str(right))
            if indent:
                ind.set(qn("w:firstLine"), str(indent))
        # pPr 자식 순서(spacing 다음 ind)를 지킨다.
        spacing = properties.find(qn("w:spacing"))
        if spacing is not None:
            spacing.addnext(ind)
        else:
            properties.append(ind)

    def largest_font_pt(self, source):
        shapes = self.model["header"]["char_shapes"]
        sizes = [shapes[shape_id]["base_size"] * shapes[shape_id]["rel_sizes"][0] / 10000
                 for _, shape_id in source["char_shape_runs"] if 0 <= shape_id < len(shapes)]
        return max(sizes, default=0)

    def page_after_shrunk_box(self, previous, current):
        """앞 문단의 표 칸 빈 공간을 지울 수 있는 빈 줄로 바꿨고, 한글에서는 현재 문단이 새 쪽에서 시작했는가.

        한 쪽을 채우던 칸이 Word에서 짧아지면 다음 표가 같은 쪽으로 올라온다. 같은 쪽이면 v_pos가
        앞 문단 끝 이상이므로, 그보다 작으면 원본의 쪽 시작이다.
        """
        if previous is None or current["header"]["break_type"] & 4:
            return False
        shrunk = getattr(self, "shrunk_tables", set())
        if not any(id(control["Table"]) in shrunk for control in previous["controls"] if "Table" in control):
            return False
        before, after = previous.get("line_segs"), current.get("line_segs")
        if not before or not after or "line_height" not in before[-1]:
            return False
        return after[0]["v_pos"] < before[-1]["v_pos"] + before[-1]["line_height"]

    def blocks(self, paragraphs, targets, nested=False):
        result, cursor, previous = [], 0, None
        for source in paragraphs:
            text, inline = plain(source)
            tables = [control["Table"] for control in source["controls"] if "Table" in control]
            new_page = not nested and self.page_after_shrunk_box(previous, source)
            previous = source
            if inline:
                if cursor >= len(targets) or targets[cursor].tag != qn("w:p"):
                    raise DomainError("VALIDATION_FAILED", "원본 문단과 Word 문단의 순서가 다릅니다.")
                target = targets[cursor]
                actual = "".join(node.text or "" for node in target.findall(".//" + qn("w:t")))
                if compact(text) != compact(actual):
                    raise DomainError("VALIDATION_FAILED", "문단의 내용을 안전하게 대응하지 못했습니다.")
                cursor += 1
                self.paragraph(target, source, page_start=True if new_page else None)
                result.append(target)
                new_page = False
            elif not tables or source["header"]["break_type"] & 4:
                target = OxmlElement("w:p")
                self.paragraph(target, source, anchor=bool(tables), page_start=True if new_page else None)
                result.append(target)
                self.restored_empty += 1
                new_page = False
            for table in tables:
                if cursor >= len(targets) or targets[cursor].tag != qn("w:tbl"):
                    raise DomainError("VALIDATION_FAILED", "원본 표와 Word 표의 순서가 다릅니다.")
                target = targets[cursor]
                cursor += 1
                self.table(target, table)
                if new_page or (result and result[-1].tag == qn("w:tbl")):
                    # Word는 사이에 문단이 없는 두 표를 하나로 합친다. 높이 없는 구분 문단으로 나눠 둔다.
                    # 원본에서 새 쪽이던 표는 이 높이 없는 문단에 쪽 나누기를 둔다.
                    separator = OxmlElement("w:p")
                    self.paragraph(separator, source, anchor=True, page_start=new_page, filler=False)
                    result.append(separator)
                    new_page = False
                result.append(target)
        for extra in targets[cursor:]:
            if extra.tag != qn("w:p") or len(extra):
                raise DomainError("VALIDATION_FAILED", "대응하지 못한 Word 문서 개체가 남았습니다.")
        return result

    @staticmethod
    def disable_east_asian_autospace(document):
        """한글은 한글·영숫자 사이에 자동 간격을 넣지 않는다. Word 기본값은 넣어 줄이 넘친다."""
        styles = document.styles.element
        defaults = styles.find(qn("w:docDefaults"))
        if defaults is None:
            defaults = OxmlElement("w:docDefaults")
            styles.insert(0, defaults)
        paragraph_default = defaults.find(qn("w:pPrDefault"))
        if paragraph_default is None:
            paragraph_default = OxmlElement("w:pPrDefault")
            defaults.append(paragraph_default)
        properties = paragraph_default.find(qn("w:pPr"))
        if properties is None:
            properties = OxmlElement("w:pPr")
            paragraph_default.append(properties)
        for name in ("w:autoSpaceDE", "w:autoSpaceDN"):
            for old in properties.findall(qn(name)):
                properties.remove(old)
            element = OxmlElement(name)
            element.set(qn("w:val"), "0")
            properties.append(element)

    @staticmethod
    def section_page(source):
        return next((c["SectionDef"].get("page") for p in source["paragraphs"] for c in p["controls"] if "SectionDef" in c), None)

    @staticmethod
    def landscape(page) -> bool:
        # HWP 용지 속성 bit0 = 가로. 치수는 세로 기준으로 저장된다.
        return bool(page.get("attr", 0) & 1)

    @classmethod
    def body_height_of(cls, page) -> int:
        """본문이 들어갈 수 있는 세로 높이(HWPUNIT)."""
        height = min(page["width"], page["height"]) if cls.landscape(page) else page["height"]
        return height - page["margin_top"] - page["margin_bottom"] - page["margin_header"] - page["margin_footer"]

    @classmethod
    def apply_page(cls, section, page):
        section.top_margin = Pt((page["margin_top"] + page["margin_header"]) / 100)
        section.bottom_margin = Pt((page["margin_bottom"] + page["margin_footer"]) / 100)
        short, long = sorted((page["width"], page["height"]))
        landscape = cls.landscape(page)
        # Word는 pgSz 너비·높이를 그대로 쓰므로 가로 용지는 값을 바꿔야 실제 가로 쪽이 된다.
        section.orientation = WD_ORIENT.LANDSCAPE if landscape else WD_ORIENT.PORTRAIT
        section.page_width = Pt((long if landscape else short) / 100)
        section.page_height = Pt((short if landscape else long) / 100)

    @staticmethod
    def content_height(cell):
        """칸 안 문단이 한글에서 실제 차지한 높이(HWPUNIT). 줄 배치 정보가 없으면 None."""
        segments = [segment for paragraph in cell["paragraphs"] for segment in paragraph.get("line_segs") or []]
        if not segments or any("line_height" not in segment for segment in segments):
            return None
        top = min(segment["v_pos"] for segment in segments)
        return max(segment["v_pos"] + segment["line_height"] for segment in segments) - top

    def blank_space(self, cells):
        """행 높이 중 내용이 채우지 않은 빈 공간을 (그 공간을 담을 칸, twips)로 찾는다.

        이 공간을 Word 최소 행 높이로 쓰면 내용을 지워도 칸이 줄지 않아 공간을 없앨 수 없다.
        """
        needs = []
        for cell in cells:
            content = self.content_height(cell)
            if content is None:
                return None
            margins = cell.get("margins") or [0, 0, 0, 0]
            needs.append((content + margins[2] + margins[3], cell))
        if not needs:
            return None
        need, owner = max(needs, key=lambda item: item[0])
        slack = round((max(cell["height"] for cell in cells) - need) / 5 * BLANK_SPACE_RATIO)
        return (owner, slack) if slack >= MIN_BLANK_TWIPS else None

    @staticmethod
    def add_blank_lines(cell, slack, valign, char_properties=None):
        """빈 공간을 글을 쓰거나 지울 수 있는 빈 문단으로 칸 정렬 방향에 맞춰 채운다."""
        count = max(1, round(slack / BLANK_LINE_TWIPS))
        lines = [slack // count] * count
        lines[-1] += slack - sum(lines)
        fillers = []
        for line in lines:
            paragraph = OxmlElement("w:p")
            properties = paragraph.get_or_add_pPr()
            spacing = properties.get_or_add_spacing()
            for name, value in (("w:before", "0"), ("w:after", "0"), ("w:line", str(max(1, line))), ("w:lineRule", "exact")):
                spacing.set(qn(name), value)
            if char_properties is not None:
                properties.append(deepcopy(char_properties))
            fillers.append(paragraph)
        above = {"top": 0, "center": count // 2, "bottom": count}[valign]
        first = next(child for child in cell if child.tag in (qn("w:p"), qn("w:tbl")))
        for paragraph in fillers[:above]:
            first.addprevious(paragraph)
        for paragraph in fillers[above:]:
            cell.append(paragraph)
        return count

    def table(self, target, source):
        origins = {(cell["row"], cell["col"]): cell for cell in source["cells"]}
        for row_index, row in enumerate(target.findall(qn("w:tr"))):
            row_cells = [cell for cell in source["cells"] if cell["row"] == row_index and cell["row_span"] == 1]
            heights = [cell["height"] for cell in row_cells]
            if heights:
                properties = row.get_or_add_trPr()
                for old in properties.findall(qn("w:trHeight")):
                    properties.remove(old)
            limit = getattr(self, "body_height", None)
            blank = self.blank_space(row_cells) if heights and not (limit and max(heights) > limit) else None
            # 한 쪽보다 큰 높이는 여러 쪽에 걸친 행의 합계다. 최소 높이로 쓰면 Word가 행을 다음 쪽으로 민다.
            if blank:
                self.shrunk_tables = getattr(self, "shrunk_tables", set()) | {id(source)}
            if heights and not (limit and max(heights) > limit) and blank is None:
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
                restored = self.blocks(original["paragraphs"], blocks, nested=True)
                for child in blocks:
                    cell.remove(child)
                cell.extend(restored)
                if not restored or restored[-1].tag != qn("w:p"):
                    cell.append(OxmlElement("w:p"))
                properties = cell.find(qn("w:tcPr"))
                for prior in properties.findall(qn("w:vAlign")):
                    properties.remove(prior)
                valign = {0: "top", 1: "center", 2: "bottom"}.get((original["list_attr"] >> 5) & 3, "top")
                align = OxmlElement("w:vAlign")
                align.set(qn("w:val"), valign)
                properties.append(align)
                if blank and blank[0] is original:
                    last = cell.findall(qn("w:p"))[-1].find(qn("w:pPr"))
                    char_properties = last.find(qn("w:rPr")) if last is not None else None
                    self.blank_lines = getattr(self, "blank_lines", 0) + self.add_blank_lines(cell, blank[1], valign, char_properties)
