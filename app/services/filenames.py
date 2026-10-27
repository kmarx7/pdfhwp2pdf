"""다운로드 표시 이름만 보존하며 서버 저장 경로와 분리한다."""
import re
import unicodedata
from urllib.parse import quote


def make_download_filename(original: str | None, output_format: str) -> str:
    extension = ".pdf" if output_format == "pdf" else ".docx"
    basename = unicodedata.normalize("NFC", (original or "").replace("\\", "/").rsplit("/", 1)[-1])
    stem = basename.rsplit(".", 1)[0] if "." in basename else basename
    stem = "".join(char for char in stem if not unicodedata.category(char).startswith("C"))
    stem = re.sub(r'[<>:"/\\|?*]', "_", stem).strip(" .")
    if stem.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        stem = "_" + stem
    stem = stem.encode("utf-8")[:240 - len(extension)].decode("utf-8", errors="ignore")
    return (stem.rstrip(" .") or "converted") + extension


def job_download_filename(job: dict) -> str:
    return make_download_filename(job.get("download_filename"), job.get("output_format", "docx"))


def content_disposition(filename: str, output_format: str) -> str:
    safe = make_download_filename(filename, output_format)
    if safe.isascii():
        return f'attachment; filename="{safe}"'
    fallback = "converted.pdf" if output_format == "pdf" else "converted.docx"
    return f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{quote(safe, safe="")}'
