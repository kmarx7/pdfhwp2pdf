"""로컬 HWP 원본과 한글에서 전체 출력한 기준 PDF를 24시간 결합한다."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.domain.errors import DomainError
from app.services.native_references import NativeReferences


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("reference", type=Path)
    args = parser.parse_args()
    settings = Settings()
    references = NativeReferences(settings.workspace.parent / "native-references", settings.native_reference_ttl)
    try:
        digest = references.register(args.source.resolve(strict=True), args.reference.resolve(strict=True))
        print(f"기준 PDF {references.lookup(digest)[1]['pages']}쪽 등록 완료. 같은 HWP 업로드에 24시간 사용할 수 있습니다.")
    except DomainError as error:
        print(f"{error.code}: {error.message}", file=sys.stderr)
        return 1
    except OSError:
        print("파일을 읽거나 기준 PDF를 저장하지 못했습니다.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
