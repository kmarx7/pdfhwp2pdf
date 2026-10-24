from pathlib import Path

import pymupdf

from app.domain.errors import DomainError
from app.domain.models import DocumentAnalysis


class FileTypeDetector:
    def detect(self, source: Path) -> str:
        with source.open("rb") as stream:
            header = stream.read(1024)
        if not header.startswith(b"%PDF-"):
            raise DomainError("INVALID_DOCUMENT", "PDF 파일의 헤더를 확인할 수 없습니다.", 400)
        return "pdf"


class DocumentAnalyzer:
    def analyze(self, source: Path, max_pages: int = 100) -> DocumentAnalysis:
        FileTypeDetector().detect(source)
        try:
            with pymupdf.open(source) as pdf:
                # 소유자 암호만 설정된 파일도 MVP에서는 보호 문서로 거부한다.
                if pdf.needs_pass or pdf.is_encrypted or pdf.metadata.get("encryption"):
                    raise DomainError("PASSWORD_PROTECTED", "암호화된 PDF는 변환할 수 없습니다.",
                                      suggestion="원본 작성 도구에서 보호를 해제한 복사본을 준비하세요.")
                if pdf.page_count == 0:
                    raise DomainError("INVALID_DOCUMENT", "페이지가 없는 PDF입니다.", 400)
                if pdf.page_count > max_pages:
                    raise DomainError("PAGE_LIMIT_EXCEEDED", f"PDF는 {max_pages}쪽까지 변환할 수 있습니다.")
                sizes, texts, fonts, ocr_pages = [], [], set(), []
                tables = 0
                warnings = ["복잡한 실무 문서의 레이아웃 및 Word 화면 품질은 아직 검증하지 않았습니다.",
                            "PDF 여백과 문단 구조는 위치 정보를 바탕으로 추정합니다."]
                if pdf.is_repaired:
                    raise DomainError("INVALID_DOCUMENT", "손상되어 자동 복구가 필요한 PDF입니다.", 400)
                for number, page in enumerate(pdf, start=1):
                    sizes.append((page.rect.width, page.rect.height))
                    text = page.get_text("text")
                    texts.append(text)
                    fonts.update(font[3] for font in page.get_fonts())
                    visible = "".join(text.split())
                    images = page.get_image_info()
                    # 이미지가 있는 무문자 페이지는 부분 변환하지 않는다.
                    # 글자 윤곽선과 빈 페이지를 확정 구별할 수 없어 보수적으로 거부한다.
                    if not visible and (images or page.get_drawings()):
                        ocr_pages.append(number)
                    # 숨은 OCR 레이어가 있는 스캔도 페이지 비트맵을 그대로 Word에
                    # 가져오는 경로로 통과시키지 않는다. 대형 배경 사진도 보수적으로 거부한다.
                    if any((pymupdf.Rect(image["bbox"]) & page.rect).get_area()
                           / max(1, page.rect.get_area()) >= 0.85 for image in images):
                        ocr_pages.append(number)
                    if visible and (text.count("\ufffd") / max(1, len(visible)) > 0.01):
                        ocr_pages.append(number)
                    # 벡터 글자와 보이지 않는 레이어는 완벽히 판별할 수 없다.
                    if page.rotation:
                        warnings.append(f"{number}쪽은 회전된 페이지입니다. 결과 배치를 확인하세요.")
                    try:
                        tables += len(page.find_tables().tables)
                    except Exception:
                        warnings.append(f"{number}쪽의 표 구조 사전 분석을 수행하지 못했습니다.")
                if ocr_pages:
                    raise DomainError("OCR_REQUIRED", "스캔 또는 읽을 수 없는 페이지에 OCR이 필요합니다.",
                                      details={"pages": sorted(set(ocr_pages))},
                                      suggestion="현재 OCR은 제공하지 않습니다. 텍스트가 포함된 PDF를 선택하세요.")
                if not any(text.strip() for text in texts):
                    raise DomainError("NO_EDITABLE_TEXT", "편집 가능한 본문 텍스트를 찾지 못했습니다.")
                if any(page.get_image_info() for page in pdf):
                    warnings.append("이미지와 텍스트가 함께 있는 페이지의 이미지 속 글자는 OCR하지 않습니다.")
                return DocumentAnalysis(pdf.page_count, sizes, texts, sorted(fonts), tables,
                                        list(dict.fromkeys(warnings)))
        except DomainError:
            raise
        except Exception as exc:
            raise DomainError("INVALID_DOCUMENT", "PDF를 열거나 분석하지 못했습니다.", 400) from exc
