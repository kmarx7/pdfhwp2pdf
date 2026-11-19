"""고정된 HWP 엔진을 프로젝트 .tools에 설치한다. 전역 환경은 변경하지 않는다."""
import argparse
import hashlib
from pathlib import Path
import platform
import shutil
import tarfile
import tempfile
from urllib.request import urlopen

VERSION = "1.3.1"
ARCHIVE = "hwp-v1.3.1-aarch64-apple-darwin.tar.gz"
EXPECTED = "60da60c55050aa9d72e74c0fe6bfc9b4ead9e3732cfb794cf0355ef8331926e4"
BINARY_HASH = "b8fe27efa4617729e22605f0e1d95f66e194c7b895e1eeadc9ad5d19300edba0"
URL = f"https://github.com/STAIxBWLB/hwp-cli/releases/download/v{VERSION}/{ARCHIVE}"
ROOT = Path(__file__).resolve().parents[1]
MEMBERS = {"hwp", "LICENSE-MIT", "LICENSE-APACHE", "NOTICE"}


def install(archive: Path) -> Path:
    if hashlib.sha256(archive.read_bytes()).hexdigest() != EXPECTED:
        raise ValueError("HWP 엔진 아카이브의 SHA-256이 일치하지 않습니다.")
    tools = ROOT / ".tools"
    if tools.is_symlink():
        raise ValueError(".tools에는 심볼릭 링크를 사용할 수 없습니다.")
    tools.mkdir(exist_ok=True)
    destination = tools / "hwp-cli" / VERSION
    if destination.is_symlink() or not destination.resolve().is_relative_to(tools.resolve()):
        raise ValueError("안전하지 않은 설치 경로입니다.")
    if destination.exists():
        if (destination / "hwp").is_file() and hashlib.sha256((destination / "hwp").read_bytes()).hexdigest() == BINARY_HASH:
            return destination / "hwp"
        raise ValueError("설치 경로에 다른 파일이 있습니다. 기존 파일을 자동 덮어쓰지 않습니다.")
    with tempfile.TemporaryDirectory(dir=tools, prefix="hwp-install-") as folder:
        staging = Path(folder)
        with tarfile.open(archive, "r:gz") as package:
            members = package.getmembers()
            if {member.name for member in members} != MEMBERS or len(members) != len(MEMBERS):
                raise ValueError("예상하지 않은 아카이브 구성입니다.")
            for member in members:
                if not member.isfile() or member.size > 50 * 1024 * 1024:
                    raise ValueError("안전하지 않은 아카이브 항목입니다.")
                with package.extractfile(member) as source, (staging / member.name).open("wb") as target:
                    shutil.copyfileobj(source, target)
        executable = staging / "hwp"
        if hashlib.sha256(executable.read_bytes()).hexdigest() != BINARY_HASH:
            raise ValueError("HWP 실행 파일의 SHA-256이 일치하지 않습니다.")
        executable.chmod(0o755)
        destination.parent.mkdir(exist_ok=True)
        staging.rename(destination)
    return destination / "hwp"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, help="공식 배포 파일을 미리 받은 경우의 로컬 경로")
    arguments = parser.parse_args()
    if (platform.system(), platform.machine()) != ("Darwin", "arm64"):
        raise SystemExit("현재 고정 배포물은 macOS Apple Silicon만 검증했습니다.")
    if arguments.archive:
        binary = install(arguments.archive)
    else:
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / ARCHIVE
            with urlopen(URL, timeout=60) as response, archive.open("wb") as target:
                shutil.copyfileobj(response, target)
            binary = install(archive)
    print(f"HWP 엔진 {VERSION} 설치 확인: {binary.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
