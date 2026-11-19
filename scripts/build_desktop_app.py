"""설치된 프로젝트를 실행하는 문서잇.app 생성. 기존 앱은 덮어쓰지 않는다."""
import argparse
from pathlib import Path
import plistlib
import shutil

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


def build_app(target: Path):
    if target.exists() or target.is_symlink():
        raise FileExistsError("기존 앱은 덮어쓰지 않습니다.")
    if target.suffix != ".app":
        raise ValueError("출력 경로는 .app이어야 합니다.")
    contents = target / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    resources = contents / "Resources"
    resources.mkdir()
    metadata = {"CFBundleName": "문서잇", "CFBundleDisplayName": "문서잇",
                "CFBundleIdentifier": "kr.kmarx.documentit.launcher", "CFBundlePackageType": "APPL",
                "CFBundleExecutable": "DocumentIt", "CFBundleIconFile": "DocumentIt.icns",
                "CFBundleVersion": "1", "CFBundleShortVersionString": "1.0",
                "LSUIElement": True, "NSHighResolutionCapable": True, "ProjectRoot": str(ROOT)}
    (contents / "Info.plist").write_bytes(plistlib.dumps(metadata))
    executable = contents / "MacOS/DocumentIt"
    executable.write_text('''#!/bin/sh
CONTENTS="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)" || exit 1
PROJECT_ROOT=$(/usr/libexec/PlistBuddy -c 'Print :ProjectRoot' "$CONTENTS/Info.plist") || exit 1
if [ ! -x "$PROJECT_ROOT/.venv/bin/python" ] || [ ! -f "$PROJECT_ROOT/scripts/launch_desktop.py" ]; then
  /usr/bin/osascript "$CONTENTS/Resources/launcher_error.applescript" "프로젝트 폴더 또는 .venv를 찾을 수 없습니다. 기존 위치에 프로젝트를 복원하거나 실행 앱을 다시 만들어 주세요."
  exit 1
fi
exec "$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/scripts/launch_desktop.py"
''')
    executable.chmod(0o755)
    shutil.copyfile(ROOT / "packaging/launcher_error.applescript", resources / "launcher_error.applescript")
    # 기존 웹앱의 녹색 문서 로고를 벡터 도형으로 그려 크기별 아이콘 생성.
    icon = Image.new("RGBA", (1024, 1024))
    draw = ImageDraw.Draw(icon)
    draw.rounded_rectangle((64, 64, 960, 960), radius=200, fill="#156e5b")
    draw.line([(334, 258), (563, 258), (690, 385), (690, 766), (334, 766), (334, 258)],
              fill="white", width=30, joint="curve")
    draw.line([(563, 258), (563, 385), (690, 385)], fill="white", width=27, joint="curve")
    for y, end in ((480, 610), (568, 610), (656, 537)):
        draw.line((416, y, end, y), fill="white", width=25)
    icon.save(resources / "DocumentIt.icns", format="ICNS")
    (contents / "PkgInfo").write_bytes(b"APPL????")
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "runtime/desktop/문서잇.app")
    args = parser.parse_args()
    print(build_app(args.output.absolute()))


if __name__ == "__main__":
    main()
