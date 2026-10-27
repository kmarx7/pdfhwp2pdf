# 문서잇 · PDF·HWP → DOCX 로컬 MVP

텍스트 기반 PDF와 HWP 5 문서를 편집 가능한 Word 문서로 변환하는 한국어 웹앱입니다. PDF 페이지를 이미지로 만들어 Word에 삽입하지 않습니다. 업로드부터 변환·검증·다운로드까지 로컬 컴퓨터에서 처리합니다.

**현재 상태: PDF MVP + HWP 5 베타 구현.** HWPX·OCR은 구현하지 않았습니다. 복잡한 실무 문서 품질과 실제 Microsoft Word 앱의 편집·렌더링은 미검증입니다. 따라서 엔진 상태는 `experimental`로 표시합니다.

**2026-10-25 v0.4.0:** HWP 웹 기본 모드를 사용자 선호 **native-embedded** 경로로 연결했습니다. 한글에서 전체 출력한 기준 PDF → pdf2docx → 로컬 글꼴 포함 순서입니다. 같은 HWP에 등록된 기준 PDF가 있으면 HWP만 올려 사용할 수 있고, 없으면 기준 PDF를 함께 선택합니다. PDF 출력 자체는 수동입니다. [웹 경로 및 실제 검증](docs/NATIVE_WEB_REPORT.md)

**HWP 레이아웃 품질 미달 확인:** 사용자 실문서를 한글 뷰어와 Word에서 비교하니 원본 16쪽이 기존 DOCX에서는 8쪽으로 표시됐습니다. 현재 HWP 직접 변환은 **편집용 초안**이며, 원본 서식 보존 요구사항을 충족했다고 판단할 수 없습니다. 빈 문단·강제 쪽 나눔·160% 줄 간격·본문 여백·표 셀 정렬/최소 높이를 부분 보완했지만, 후보 결과도 글꼴과 페이지 배치가 달랐습니다. 자동 테스트 통과·텍스트 보존율은 시각 품질 합격이 아닙니다. [실제 Word 검토 보고서](docs/HWP_LAYOUT_REVIEW.md)

## 실행

이 Mac에서는 바탕화면의 **문서잇.app**을 더블클릭하면 서버를 시작하고 기본 브라우저를 엽니다. 이미 이 프로젝트 서버가 실행 중이면 재사용합니다. 터미널을 열 필요가 없으며 브라우저를 닫아도 서버는 백그라운드에 남습니다. 다른 프로그램이 8000번 포트를 사용하면 종료하지 않고 오류를 표시합니다.

실행 앱 재생성: `.venv/bin/python scripts/build_desktop_app.py` → `runtime/desktop/문서잇.app`을 Finder에서 바탕화면으로 복사합니다. 기존 앱은 덮어쓰지 않습니다. 실행 앱은 현재 프로젝트 위치와 `.venv`를 참조하므로 프로젝트를 이동하면 다시 생성해야 합니다. 로그는 `runtime/desktop-launcher/server.log`에 남고 다음 시작 시 5 MiB 초과 로그를 한 번 회전합니다. 로그인 자동 실행은 등록하지 않습니다.

Python 3.11을 사용합니다. 시스템 Python이나 다른 프로젝트 환경은 변경하지 않습니다.

```bash
git clone https://github.com/kmarx7/pdfhwp2pdf.git
cd pdfhwp2pdf
git switch feat/native-web-conversion
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python scripts/install_hwp_engine.py
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

브라우저에서 **http://127.0.0.1:8000** 을 엽니다. 이 작업 폴더에는 이미 `.venv`와 의존성이 설치되어 있으므로 마지막 서버 명령만 실행하면 됩니다. 서버를 이미 실행 중이면 중복 실행하지 않습니다. 종료는 서버 터미널의 `Ctrl+C`입니다.

Node.js가 있는 환경에서는 `npm run dev`도 동일한 서버를 실행합니다. 코드 갱신 후에는 `npm run dev -- --restart`로 이 프로젝트의 서버만 확인해 재시작할 수 있습니다. npm 패키지 설치나 프런트엔드 빌드는 필요하지 않습니다. 작업 저장소는 단일 서버 프로세스로만 사용할 수 있습니다. `--workers 2`나 외부 주소 바인딩은 지원하지 않습니다.

이번 검증 환경은 macOS 27.0.1 / Apple Silicon arm64 / Python 3.11.15입니다. 일반 pip/uv의 DNS 연결이 실패해 공식 PyPI wheel을 직접 내려받은 뒤 `.venv`에 오프라인 설치했습니다. `pip check` 및 import·변환 검사를 통과했습니다. lock은 검증 환경의 전체 패키지 버전을 고정한 파일이며 플랫폼별 wheel hash lock은 아닙니다. Linux·Docker 호환성은 아직 실행 검증하지 않았습니다.

## 사용 방법

1. **PDF → Word / HWP → Word 베타**를 선택하고 파일 한 개를 업로드합니다. 드롭한 파일의 확장자로 선택 형식도 바뀝니다.
2. 파일명·크기를 확인합니다. HWP의 기본은 **원본 PDF 기준 · 글꼴 포함**(`native_embedded`)입니다. 등록 PDF가 없으면 한글 뷰어에서 같은 문서의 전체 페이지를 PDF로 저장해 **기준 PDF 선택**으로 추가합니다. 기준 PDF가 준비되어야 변환 버튼이 활성화됩니다. PDF 입력 기본과 HWP의 명시적 **편집용 초안 변환**은 `balanced`입니다.
3. 분석→변환→서식 정리→검증 상태를 확인합니다. 엔진의 정확한 페이지 진행률을 얻을 수 없어 가짜 백분율은 표시하지 않습니다.
4. 성공하면 **Word 파일 다운로드**를 누릅니다. 결과 파일명은 항상 `converted.docx`입니다. 검증 정보와 경고도 확인할 수 있습니다.
   로컬 macOS에서는 다운로드 요청 후 **다운로드 폴더 열기** 버튼이 나타납니다. Finder로 기본 `~/Downloads`를 엽니다. 브라우저의 사용자 지정 저장 경로나 저장 완료 여부는 웹앱에서 확인할 수 없으므로, 다른 위치에 저장했다면 브라우저 다운로드 목록에서 확인하세요. 다운로드를 취소해도 버튼은 나타날 수 있습니다. Linux에서는 폴더 열기 버튼을 표시하지 않습니다.
5. 작업 취소·다른 파일 변환 시 해당 작업의 복사본과 결과를 삭제합니다. 원본 파일은 변경하지 않습니다.

변환된 DOCX에 본문 `w:t`와 실제 Word 표 `w:tbl`이 존재하는지 검사합니다. 원본에서 추출한 문자의 99% 미만이 남거나 중복이 1%를 넘으면 실패시킵니다. 이 검사는 문자 집합 기반의 누락 탐지이며 읽기 순서·실제 CER·시각 유사도를 증명하지 않습니다.

## 테스트

최신 웹 연결·검증 상태는 [웹 경로 보고서](docs/NATIVE_WEB_REPORT.md)에 기록했습니다. 이전 CLI 단계 이력은 [인수인계](docs/HANDOFF.md)를 참고하세요. 웹앱과 같은 PDF·글꼴 처리 경로를 독립 실행하는 도구도 유지합니다.

```bash
# 한글 뷰어에서 원본을 텍스트가 포함된 PDF로 먼저 저장합니다.
.venv/bin/python scripts/convert_reference_pdf.py /path/to/reference.pdf runtime/results/native-embedded.docx
# 기본 macOS 글꼴 폴더 이외의 글꼴을 사용할 때 (반복 지정 가능)
.venv/bin/python scripts/convert_reference_pdf.py /path/to/reference.pdf runtime/results/another.docx --font-dir /path/to/fonts
# 같은 HWP에서 기준 PDF를 반복 사용하려면 로컬에 24시간 등록합니다.
.venv/bin/python scripts/register_native_reference.py /path/to/source.hwp /path/to/reference.pdf
```

기본 검색 위치는 설치된 한글 뷰어의 TTF 폴더와 사용자 `~/Library/Fonts`입니다. 글꼴을 새로 설치하지 않으며, 문서에 쓰인 글꼴을 찾지 못하거나 편집용 포함 플래그를 확인할 수 없으면 실패합니다. 글꼴 전체를 포함해 출력이 커질 수 있습니다. 기존 결과는 덮어쓰지 않고 `.quality.json` 보고서를 함께 저장합니다. 실제 페이지 배치 보존을 자동으로 합격 처리하지 않습니다. [로컬 경로 명세](docs/NATIVE_PDF_WORKFLOW.md)

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m pip check
.venv/bin/python scripts/probe_environment.py --smoke
node --check app/frontend/static/app.js
```

합성 영문·한글·표·이미지·다페이지 PDF, DOCX 텍스트·표 개체와 수정/저장·재열기, 손상·암호화·스캔/혼합/OCR 레이어 PDF 거부, 파일명·MIME, 업로드 제한·CSRF, 취소·만료·재시작·변조·자원 제한을 자동 검사합니다. pytest가 임시 폴더에 문서를 생성하므로 별도 샘플은 필요하지 않습니다.

직접 시험할 PDF를 생성하려면 다음 명령을 사용합니다. 대상 폴더에 같은 이름의 fixture가 있으면 덮어쓰지 않습니다.

```bash
.venv/bin/python scripts/make_test_pdfs.py --output-dir runtime/my-samples
```

`runtime/`과 `.tools/`는 git에서 제외합니다. PDF 검증은 [2단계 보고서](docs/STAGE2_REPORT.md), HWP 설치·테스트·브라우저 검증과 제한은 [HWP 보고서](docs/HWP_REPORT.md)를 참고하세요.

다운로드 폴더 버튼의 동작·제한·77개 테스트 결과는 [다운로드 폴더 보고서](docs/DOWNLOAD_FOLDER_REPORT.md)에 기록했습니다.

## HWP 5 베타 지원

`hwp-cli 1.3.1`의 macOS arm64 공식 배포물을 프로젝트 `.tools/hwp-cli/1.3.1/`에 고정 설치합니다. Python·Java·Office 전역 설치는 추가하지 않습니다. 다운로드는 설치할 때 GitHub에서 실행 파일을 받는 용도이며, 사용자 문서를 외부로 전송하지 않습니다. 바이너리와 아카이브의 SHA-256을 확인하고 라이선스/NOTICE를 함께 보관합니다. Linux/Intel용 HWP 엔진은 아직 활성화하지 않았습니다.

```bash
.venv/bin/python scripts/install_hwp_engine.py
# 네트워크 제한 환경에서 공식 배포물을 미리 받은 경우
.venv/bin/python scripts/install_hwp_engine.py --archive /path/to/hwp-v1.3.1-aarch64-apple-darwin.tar.gz
# 직접 시험할 합성 HWP 16개 생성 (기존 파일 덮어쓰기 없음)
.venv/bin/python scripts/make_test_hwps.py --output-dir runtime/my-hwp-samples
```

지원: 본문 텍스트·기본 글꼴/크기/색상, 일반 표와 가로/세로 셀 병합, 열 너비, 실선/선 없음 테두리·단색 셀 배경·셀 여백, 원본 이미지 바이트와 인라인 이미지, 섹션 페이지 크기. 텍스트·표·이미지 누락 및 표 구조/치수 검사를 통과한 결과만 다운로드합니다.

후속 표 서식 보완: 점선·이중선 테두리를 지원합니다. 두 색상의 선형 그라데이션은 중간색 단색으로 **근사**하고 화면·품질 보고서에 서식 손실 경고를 표시합니다. 그라데이션 자체를 보존하는 기능은 아닙니다. 행별 열 치수 불일치는 3pt 이내에서 개별 열 셀을 우선해 정규화하고, 0.1pt를 넘는 조정을 경고합니다. 더 큰 불일치는 계속 거부합니다. 원본 한 건의 실제 변환 결과와 82개 테스트 증거는 [표 서식 보완 보고서](docs/HWP_TABLE_REPORT.md)를 참고하세요.

쪽 번호: 구역 시작의 위·아래 왼쪽/가운데/오른쪽 배치, 아라비아·로마·영문 번호와 앞뒤 장식 문자를 Word의 자동 `PAGE` 필드로 옮깁니다. 문서 시작 번호와 구역 간 설정 유지/해제를 반영합니다. Word에서 필드를 업데이트한 뒤 확인하세요. 번호 결과 캐시는 넣지 않으므로 필드를 계산하지 않는 미리보기에서는 번호가 비어 보일 수 있습니다. 실제 Word의 번호 표시·페이지 나눔·글꼴은 미검증입니다.

현재 거부: HWP 3.x, 암호·배포용·DRM 등 보호 플래그, 머리말·꼬리말·수식·도형·다단·필드·각주 등 미지원 control, 알 수 없는 본문 레코드, 복잡한 표 배경·테두리, 확인할 수 없는 이미지 참조. `--strict`만으로 DOCX 손실을 검사할 수 없어 자체 분석·후처리·검증을 추가했습니다.

표 배경 중 그림·무늬·복합 채우기, 방사형/다중 색상 그라데이션은 계속 거부합니다. 점선·이중선 이외의 추가 선 모양도 아직 지원하지 않습니다.

쪽 번호도 안쪽·바깥쪽 교대 배치, 본문 중간에서 설정 변경, 표 안 설정, 번호 감추기·재시작 컨트롤, 원문자 등 미지원 숫자 모양은 계속 거부합니다. 위의 머리말·꼬리말 미지원은 원본의 일반 머리말·꼬리말 컨트롤을 뜻하며, 지원하는 쪽 번호를 배치하기 위한 DOCX 머리말·꼬리말 생성과 구분합니다.

HWP의 정확한 페이지 나눔·부유 배치·이미지 회전/자르기·글꼴 설치 상태와 실제 Word 화면은 미검증입니다. 원본 보존·복사본 삭제·1시간 결과 보관 정책은 PDF와 같습니다. 엔진이 없으면 PDF 기능은 계속 동작하며 HWP 변환 버튼은 비활성화됩니다.

## 파일 수명·제한

- 파일 최대 30 MiB, PDF 최대 100쪽(HWP는 페이지 수를 추정하지 않음), 변환 동시 1개·대기 최대 5개입니다.
- 작업당 180초, 작업 프로세스 RSS 1 GiB, 전체 작업 폴더 1 GiB를 상한으로 감시합니다. RSS 감시는 50ms 간격의 최선 노력 제한이며 Linux cgroup 같은 강제 격리는 아닙니다.
- 업로드 복사본은 `runtime/jobs/<uuid>/input/`에 읽기 전용으로 보관합니다. 작업 종료 후 입력·중간 파일을 삭제하고, 실패 시 부분 DOCX도 삭제합니다.
- 성공 DOCX·품질 보고서는 완료 후 1시간 보관합니다. 조회·다운로드로 연장하지 않습니다. 만료 시 즉시 접근을 차단하고 60초 간격으로 정리합니다.
- 등록 기준 PDF는 별도 `runtime/native-references/<HWP SHA-256>/`에 24시간, 전체 256 MiB까지 보관합니다. 조회·사용으로 연장하지 않고 서버 시작/정리 주기에 삭제합니다. 첨부 PDF는 해당 작업 종료 후 삭제하며 자동 등록하지 않습니다. HWP/PDF 각각 30 MiB, 기준 PDF 100쪽 제한이며, 글꼴 포함 결과는 업로드 제한보다 클 수 있습니다.
- 다운로드 중에는 최대 60초 동안 삭제를 보류합니다. 삭제·만료 후에는 내용 없는 tombstone을 24시간 보관해 410 응답을 구분합니다.
- **서버가 꺼져 있으면 정리 작업도 멈추며, 남은 파일은 다음 실행 때 정리합니다.** 일반 파일 삭제이며 저장장치 보안 소거를 보장하지 않습니다.

## 지원 범위와 한계

- 단순 디지털 PDF의 텍스트·표·이미지·페이지 크기를 첫 지원 범위로 둡니다. 합성 테스트 통과를 모든 PDF의 품질 보장으로 표현하지 않습니다.
- 스캔·혼합 PDF, 페이지 대부분을 차지하는 이미지(숨은 OCR 레이어 포함)는 `OCR_REQUIRED`로 거부합니다. 이미지 속 일부 글자를 완전히 탐지할 수는 없습니다.
- 암호화 PDF는 사용자 암호 유무와 관계없이 거부합니다. 손상되어 자동 복구가 필요한 PDF, 빈 문서, 100쪽 초과 입력도 명확한 오류를 반환합니다.
- 복잡한 다단, 병합·중첩 표, 부유 이미지, 글꼴 대체, 제목 스타일, 머리말·꼬리말·필드의 정확한 복원은 미검증입니다. PDF 경로의 `python-docx` 후처리는 문서 개인 속성 정리에 사용합니다. HWP의 별도 표 후처리 범위는 위 베타 지원 설명을 참고하세요.
- 실제 Word 수동 편집·시각 비교·6개 실문서 corpus의 품질 관문은 남아 있습니다. PDF 분석기와 변환기의 공통 추출 오류를 현재 검증기가 모두 잡아낼 수는 없습니다.
- localhost 단일 사용자용입니다. Host/Origin·CSRF 검사를 적용했지만 공개 서비스용 인증·사용자별 격리·네트워크 sandbox는 제공하지 않습니다.
- `pdf2docx`는 [Artifex의 적극적인 유지보수가 중단](https://github.com/ArtifexSoftware/pdf2docx/discussions/374)되었습니다. 엔진을 독립 클래스로 분리하고 의존성을 고정했습니다.
- PyMuPDF는 [AGPL/상용 이중 라이선스](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright)입니다. `pdf2docx`의 MIT가 전이 의존성 전체에 적용되는 것은 아닙니다. 유료 계약·클라우드·외부 API·DB는 추가하지 않았습니다.

## 구조와 API

```text
app/
  main.py                  # FastAPI · API · 다운로드 · lifespan
  api/security.py          # 본문 크기 · Host/Origin · CSRF
  services/                # PDF 분석 · 엔진 선택 · 작업 큐/저장소/정리
  engines/base.py          # 교체 가능한 변환 인터페이스
  engines/pdf/             # Pdf2DocxEngine
  engines/hwp/             # 고정된 hwp-cli 실행·무결성 검사·변환 어댑터
  infrastructure/          # 격리 worker · 안전한 작업 경로
  postprocess/             # 문서 속성·HWP 표 너비/기본 테두리·배경 후처리
  quality/                 # DOCX 텍스트·표·문자 보존 검사
  frontend/                # 한국어 HTML/CSS/JavaScript
scripts/                   # 환경 probe · 합성 PDF/HWP 생성 · HWP 엔진 설치
tests/                     # 실제 엔진 및 API 자동 테스트
```

| API | 기능 |
| --- | --- |
| `GET /api/v1/health` | 서버 상태 |
| `GET /api/v1/capabilities` | PDF/HWP 엔진·제한·experimental 상태 |
| `GET /api/v1/session` | HttpOnly 세션 쿠키와 CSRF 토큰 |
| `POST /api/v1/desktop/open-downloads` | 로컬 macOS 기본 다운로드 폴더 열기; CSRF 필요, 경로·옵션 본문 거부 |
| `POST /api/v1/jobs` | multipart `file`, `mode=balanced`, `ocr=off`; `X-CSRF-Token` 필요 |
| `POST /api/v1/native/jobs` | multipart `file`, HWP는 선택적 `reference` PDF; `native_embedded` 고정, CSRF 필요 |
| `GET /api/v1/native/references/{sha256}` | 같은 HWP의 유효한 등록 PDF 존재·쪽 수·만료 시각 조회; 로컬 경로 비공개 |
| `GET /api/v1/jobs/{uuid}` | 상태·오류·결과 링크 |
| `GET /api/v1/jobs/{uuid}/download` | DOCX 다운로드 |
| `GET /api/v1/jobs/{uuid}/quality` | 구조 검증 보고서 |
| `DELETE /api/v1/jobs/{uuid}` | 취소·삭제; `X-CSRF-Token` 필요 |

접수는 202로 반환하며, 이후 암호화·OCR·변환 실패는 작업 상태 `failed`와 한국어 오류로 전달합니다. 실패 작업은 다운로드할 수 없습니다.

설계 문서: [PRD](docs/PRD.md), [ARCHITECTURE](docs/ARCHITECTURE.md), [CONVERSION_SPEC](docs/CONVERSION_SPEC.md), [TEST_PLAN](docs/TEST_PLAN.md), [AGENTS](AGENTS.md).

다음 권장 단계는 실문서 corpus·Word 수동 편집 검증, 읽기 순서·표 셀/스타일 품질 평가, 원본/결과 비교와 글꼴 정책 검증입니다. 기능이 달라지는 작업은 별도 Git 브랜치에서 진행합니다.
