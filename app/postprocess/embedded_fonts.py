"""설치된 로컬 글꼴의 editable embedding 권한을 확인한 뒤 DOCX에 포함한다.

글꼴을 설치·수정하지 않으며 글꼴 파일 자체를 저장소에 배포하지 않는다.
"""
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED

from fontTools.ttLib import TTFont
from lxml import etree

from app.domain.errors import DomainError

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
P = "{http://schemas.openxmlformats.org/package/2006/relationships}"
C = "{http://schemas.openxmlformats.org/package/2006/content-types}"
FONT_MIME = "application/vnd.openxmlformats-officedocument.obfuscatedFont"


def embedding_allowed(flags: int) -> bool:
    # Preview/Print(4)는 편집용 문서의 허용 권한으로 취급하지 않는다.
    # No subsetting(256)은 전체 글꼴을 넣으므로 허용한다.
    return not flags & (2 | 4 | 512) and not flags & ~0x030E


def key(name: str) -> str:
    return "".join(name.casefold().split()).replace("-", "")


def obfuscate(data: bytes, font_key: str) -> bytes:
    if len(data) < 32:
        raise DomainError("INVALID_FONT", "글꼴 파일이 너무 짧습니다.")
    mask = bytes.fromhex(font_key.strip("{}").replace("-", ""))[::-1]
    output = bytearray(data)
    for index in range(32):
        output[index] ^= mask[index % 16]
    return bytes(output)


@dataclass(frozen=True)
class LocalFont:
    path: Path
    family: str
    aliases: frozenset[str]
    bold: bool
    flags: int


def local_fonts(directories: list[Path]) -> list[LocalFont]:
    files = sorted({p.resolve() for directory in directories if directory.is_dir()
                    for p in directory.rglob("*") if p.suffix.lower() in {".ttf", ".otf"}
                    and p.is_file() and not p.is_symlink()})
    if len(files) > 2000:
        raise DomainError("RESOURCE_LIMIT", "글꼴 검색 파일 수가 2,000개를 넘었습니다.")
    result = []
    for path in files:
        if path.stat().st_size > 50 * 1024 * 1024:
            continue
        try:
            with TTFont(path, lazy=True) as font:
                names = font["name"]
                family = names.getBestFamilyName() or names.getDebugName(1)
                if not family:
                    continue
                aliases = frozenset(key(n.toUnicode()) for n in names.names if n.nameID in {1, 4, 6, 16})
                bold = bool(font["OS/2"].fsSelection & (1 << 5))
                result.append(LocalFont(path, key(family), aliases, bold, font["OS/2"].fsType))
        except Exception:
            continue  # 읽을 수 없는 글꼴을 임의로 포함하지 않는다.
    return sorted(result, key=lambda font: (font.bold, str(font.path)))


def embed_local_fonts(source: Path, target: Path, directories: list[Path]) -> dict:
    if target.exists():
        raise FileExistsError("출력 DOCX가 이미 존재합니다.")
    with ZipFile(source) as package:
        if sum(item.file_size for item in package.infolist()) > 256 * 1024 * 1024:
            raise DomainError("RESOURCE_LIMIT", "DOCX의 압축 해제 크기가 제한을 초과했습니다.")
        parts = {name: package.read(name) for name in package.namelist()}
    if any(name.startswith("word/fonts/") for name in parts):
        raise DomainError("ALREADY_EMBEDDED", "이미 글꼴이 포함된 DOCX는 다시 처리하지 않습니다.")
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    document = etree.fromstring(parts["word/document.xml"], parser)
    aliases = sorted({node.get(W + name) for node in document.iter(W + "rFonts")
                      for name in ("ascii", "hAnsi", "eastAsia", "cs") if node.get(W + name)})
    catalog = local_fonts(directories)
    matches = {}
    for alias in aliases:
        font = next((font for font in catalog if key(alias) in font.aliases), None)
        if font is None:
            raise DomainError("FONT_NOT_FOUND", "문서에 사용된 로컬 글꼴을 찾지 못했습니다.",
                              details={"font": alias}, suggestion="해당 글꼴이 있는 폴더를 --font-dir로 지정하세요.")
        bold = font if font.bold else next((item for item in catalog if item.family == font.family and item.bold), font)
        if not all(embedding_allowed(item.flags) for item in (font, bold)):
            raise DomainError("FONT_EMBEDDING_DENIED", "편집용 포함 권한을 확인할 수 없는 글꼴입니다.", details={"font": alias})
        matches[alias] = (font, bold)
    unique = {font.path for pair in matches.values() for font in pair}
    if sum(path.stat().st_size for path in unique) > 200 * 1024 * 1024:
        raise DomainError("RESOURCE_LIMIT", "포함할 글꼴 합계가 200 MiB를 넘었습니다.")
    table = etree.fromstring(parts["word/fontTable.xml"], parser)
    rel_name = "word/_rels/fontTable.xml.rels"
    rels = etree.fromstring(parts[rel_name], parser) if rel_name in parts else etree.Element(P + "Relationships", nsmap={None: P[1:-1]})
    embedded = {}
    for alias, pair in matches.items():
        for old in list(table):
            if old.get(W + "name") == alias:
                table.remove(old)
        entry = etree.SubElement(table, W + "font", {W + "name": alias})
        for tag, info in zip(("embedRegular", "embedBold"), pair):
            if info.path not in embedded:
                font_key = "{" + str(uuid4()).upper() + "}"
                name = f"fonts/native-{len(embedded) + 1}.odttf"
                parts["word/" + name] = obfuscate(info.path.read_bytes(), font_key)
                embedded[info.path] = (name, font_key)
            name, font_key = embedded[info.path]
            rid = "rIdNative" + uuid4().hex
            etree.SubElement(rels, P + "Relationship", {"Id": rid, "Type": R[1:-1] + "/font", "Target": name})
            etree.SubElement(entry, W + tag, {R + "id": rid, W + "fontKey": font_key, W + "subsetted": "false"})
    types = etree.fromstring(parts["[Content_Types].xml"], parser)
    if not any(node.get("Extension") == "odttf" for node in types):
        etree.SubElement(types, C + "Default", {"Extension": "odttf", "ContentType": FONT_MIME})
    for name, root in (("word/fontTable.xml", table), (rel_name, rels), ("[Content_Types].xml", types)):
        parts[name] = etree.tostring(root, encoding="UTF-8", xml_declaration=True, standalone=True)
    created = False
    try:
        with ZipFile(target, "x", ZIP_DEFLATED) as package:
            created = True
            for name, content in parts.items():
                package.writestr(name, content)
    except Exception:
        if created:
            target.unlink(missing_ok=True)
        raise
    return {"embedded_font_count": len(embedded), "aliases": aliases, "full_fonts": True,
            "editable_embedding_flags_checked": True}
