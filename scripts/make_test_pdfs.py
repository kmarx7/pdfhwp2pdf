"""실무 품질을 대표하지 않는 합성 PDF fixture를 생성한다."""
import argparse
from pathlib import Path

import pymupdf


def make_test_pdfs(folder: Path) -> dict[str, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    result = {}
    for name in ("text", "table", "korean", "multipage", "image", "encrypted", "owner_protected", "scanned", "mixed", "ocr_layer", "blank"):
        target = folder / f"{name}.pdf"
        if target.exists():
            raise FileExistsError(f"Fixture already exists: {target.name}")
        with pymupdf.open() as document:
            page = document.new_page(width=595, height=842)
            if name != "blank":
                page.insert_text((60, 70), "Editable PDF conversion", fontsize=20, fontname="hebo")
                page.insert_text((60, 110), "A real paragraph for Word editing. Reference 12345.", fontsize=12)
            if name == "table":
                for y in (160, 200, 240, 280):
                    page.draw_line((60, y), (510, y), color=(0, 0, 0), width=1)
                for x in (60, 280, 510):
                    page.draw_line((x, 160), (x, 280), color=(0, 0, 0), width=1)
                for x, y, text in ((75, 185, "Item"), (295, 185, "Amount"),
                                   (75, 225, "Alpha"), (295, 225, "100"),
                                   (75, 265, "Beta"), (295, 265, "200")):
                    page.insert_text((x, y), text, fontsize=12)
            if name == "korean":
                page.insert_text((60, 160), "한글 문서 변환 테스트", fontname="korea", fontsize=18)
                page.insert_text((60, 200), "본문과 표를 편집 가능한 문서로 변환합니다.", fontname="korea", fontsize=12)
            if name == "multipage":
                page = document.new_page(width=842, height=595)
                page.insert_text((60, 70), "Second landscape page 67890.", fontsize=14)
            if name == "image":
                pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 160, 100), False)
                pixmap.clear_with(160)
                page.insert_image(pymupdf.Rect(60, 160, 220, 260), stream=pixmap.tobytes("png"))
            if name in {"scanned", "mixed", "ocr_layer"}:
                png = page.get_pixmap().tobytes("png")
                if name in {"scanned", "ocr_layer"}:
                    document.delete_page(0)
                page = document.new_page(width=595, height=842)
                page.insert_image(page.rect, stream=png)
                if name == "ocr_layer":
                    page.insert_text((60, 70), "Hidden OCR text on a scanned page", render_mode=3)
            kwargs = {}
            if name in {"encrypted", "owner_protected"}:
                kwargs = {"encryption": pymupdf.PDF_ENCRYPT_AES_256,
                          "owner_pw": "test-owner-only", "user_pw": "test-password" if name == "encrypted" else ""}
            document.save(target, **kwargs)
        result[name] = target
    result["invalid"] = folder / "invalid.pdf"
    result["invalid"].write_bytes(b"%PDF-1.7\nnot a valid document\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("runtime/samples"))
    args = parser.parse_args()
    paths = make_test_pdfs(args.output_dir)
    print(f"합성 PDF {len(paths)}개 생성: {args.output_dir}")
