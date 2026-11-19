"""같은 HWP의 SHA-256에 결합한 원본 출력 PDF만 24시간 재사용한다."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import time

from app.domain.errors import DomainError
from app.infrastructure.workspace import atomic_json, directory_bytes


class NativeReferences:
    def __init__(self, root: Path, ttl=86400, clock=time.time):
        if root.is_symlink():
            raise ValueError("Unsafe reference root")
        self.root = root.resolve()
        self.ttl, self.clock = ttl, clock

    def entry(self, digest: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise DomainError("INVALID_REQUEST", "원본 식별 값이 올바르지 않습니다.", 400)
        path = self.root / digest
        if path.is_symlink() or (path.exists() and any(p.is_symlink() for p in path.rglob("*"))):
            raise DomainError("REFERENCE_INVALID", "등록된 기준 PDF의 경로를 확인할 수 없습니다.")
        return path

    def lookup(self, digest: str) -> tuple[Path, dict] | None:
        path = self.entry(digest)
        if not path.is_dir():
            return None
        try:
            meta = json.loads((path / "meta.json").read_text())
            if meta["expires_at"] <= self.clock():
                shutil.rmtree(path)
                return None
            pdf = path / "reference.pdf"
            if hashlib.sha256(pdf.read_bytes()).hexdigest() != meta["pdf_sha256"]:
                raise ValueError("checksum mismatch")
            return pdf, meta
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise DomainError("REFERENCE_INVALID", "등록된 기준 PDF의 무결성을 확인하지 못했습니다.") from error

    def register(self, source: Path, pdf: Path):
        from app.services.hwp_analyzer import HwpAnalyzer
        from app.services.analyzer import DocumentAnalyzer
        from app.services.native_validation import validate_reference_text
        if source.stat().st_size > 30 * 1024 * 1024 or pdf.stat().st_size > 30 * 1024 * 1024:
            raise DomainError("FILE_TOO_LARGE", "원본과 기준 PDF는 각각 30 MiB까지 등록할 수 있습니다.")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        pdf_digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
        existing = self.lookup(digest)
        if existing:
            if existing[1]["pdf_sha256"] == pdf_digest:
                return digest
            raise DomainError("REFERENCE_CONFLICT", "이 HWP에 다른 기준 PDF가 이미 등록되어 있습니다.")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if directory_bytes(self.root) + pdf.stat().st_size > 256 * 1024 * 1024:
            raise DomainError("RESOURCE_LIMIT", "등록 기준 PDF 저장 공간이 부족합니다.")
        with tempfile.TemporaryDirectory(dir=self.root, prefix=".register-") as folder:
            work = Path(folder)
            original = HwpAnalyzer().analyze(source, work)
            reference = DocumentAnalyzer().analyze(pdf)
            validate_reference_text(original, reference)
            shutil.copyfile(pdf, work / "reference.pdf")
            if hashlib.sha256((work / "reference.pdf").read_bytes()).hexdigest() != pdf_digest:
                raise DomainError("REFERENCE_INVALID", "기준 PDF 복사본의 무결성이 다릅니다.")
            if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
                raise DomainError("REFERENCE_INVALID", "등록 중 원본 HWP의 내용이 변경되었습니다.")
            (work / "source-model.json").unlink(missing_ok=True)
            atomic_json(work / "meta.json", {"pdf_sha256": pdf_digest, "pages": reference.pages,
                                           "expires_at": self.clock() + self.ttl})
            # 고유 HWP 해시별 등록. 기존 다른 기준을 덮어쓰지 않는다.
            work.rename(self.entry(digest))
        return digest

    def cleanup(self):
        if self.root.is_dir():
            for path in self.root.iterdir():
                if re.fullmatch(r"[0-9a-f]{64}", path.name):
                    try:
                        self.lookup(path.name)
                    except DomainError:
                        # 한 항목의 변조가 다른 항목의 만료 정리를 막지 않는다.
                        continue
