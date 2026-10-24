# 문서잇 · PDF → DOCX 로컬 MVP

텍스트 기반 PDF를 편집 가능한 Word 문서로 변환하는 한국어 웹앱입니다. PDF 페이지를 이미지로 만들어 Word에 삽입하지 않습니다. 업로드부터 변환·검증·다운로드까지 로컬 컴퓨터에서 처리합니다.

**현재 상태: PDF MVP 구현, 합성 문서 자동 검증 완료.** HWP/HWPX·OCR은 구현하지 않았습니다. 복잡한 실무 문서 품질과 실제 Microsoft Word 앱의 편집·렌더링은 미검증입니다. 따라서 엔진 상태는 `experimental`로 표시합니다.

## 실행

Python 3.11을 사용합니다. 시스템 Python이나 다른 프로젝트 환경은 변경하지 않습니다.

```bash
git clone https://github.com/kmarx7/pdfhwp2pdf.git
cd pdfhwp2pdf
git switch feat/pdf-docx-mvp
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

브라우저에서 **http://127.0.0.1:8000** 을 엽니다. 이 작업 폴더에는 이미 `.venv`와 의존성이 설치되어 있으므로 마지막 서버 명령만 실행하면 됩니다. 서버를 이미 실행 중이면 중복 실행하지 않습니다. 종료는 서버 터미널의 `Ctrl+C`입니다.

Node.js가 있는 환경에서는 `npm run dev`도 동일한 서버를 실행합니다. npm 패키지 설치나 프런트엔드 빌드는 필요하지 않습니다. 작업 저장소는 단일 서버 프로세스로만 사용할 수 있습니다. `--workers 2`나 외부 주소 바인딩은 지원하지 않습니다.

이번 검증 환경은 macOS 27.0.1 / Apple Silicon arm64 / Python 3.11.15입니다. 일반 pip/uv의 DNS 연결이 실패해 공식 PyPI wheel을 직접 내려받은 뒤 `.venv`에 오프라인 설치했습니다. `pip check` 및 import·변환 검사를 통과했습니다. lock은 검증 환경의 전체 패키지 버전을 고정한 파일이며 플랫폼별 wheel hash lock은 아닙니다. Linux·Docker 호환성은 아직 실행 검증하지 않았습니다.

## 사용 방법

1. PDF 한 개를 드래그하거나 파일 선택 버튼으로 업로드합니다.
2. 파일명·크기를 확인하고 **Word로 변환하기**를 누릅니다. 현재 `balanced` 모드만 제공합니다.
3. 분석→변환→서식 정리→검증 상태를 확인합니다. 엔진의 정확한 페이지 진행률을 얻을 수 없어 가짜 백분율은 표시하지 않습니다.
4. 성공하면 **Word 파일 다운로드**를 누릅니다. 결과 파일명은 항상 `converted.docx`입니다. 검증 정보와 경고도 확인할 수 있습니다.
5. 작업 취소·다른 파일 변환 시 해당 작업의 복사본과 결과를 삭제합니다. 원본 파일은 변경하지 않습니다.

변환된 DOCX에 본문 `w:t`와 실제 Word 표 `w:tbl`이 존재하는지 검사합니다. 원본에서 추출한 문자의 99% 미만이 남거나 중복이 1%를 넘으면 실패시킵니다. 이 검사는 문자 집합 기반의 누락 탐지이며 읽기 순서·실제 CER·시각 유사도를 증명하지 않습니다.

## 테스트

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

`runtime/`은 git에서 제외합니다. 테스트·브라우저 결과와 남은 검증 범위는 [2단계 검증 보고서](docs/STAGE2_REPORT.md)에 있습니다.

## 파일 수명·제한

- 파일 최대 30 MiB, PDF 최대 100쪽, 변환 동시 1개·대기 최대 5개입니다.
- 작업당 180초, 작업 프로세스 RSS 1 GiB, 전체 작업 폴더 1 GiB를 상한으로 감시합니다. RSS 감시는 50ms 간격의 최선 노력 제한이며 Linux cgroup 같은 강제 격리는 아닙니다.
- 업로드 복사본은 `runtime/jobs/<uuid>/input/`에 읽기 전용으로 보관합니다. 작업 종료 후 입력·중간 파일을 삭제하고, 실패 시 부분 DOCX도 삭제합니다.
- 성공 DOCX·품질 보고서는 완료 후 1시간 보관합니다. 조회·다운로드로 연장하지 않습니다. 만료 시 즉시 접근을 차단하고 60초 간격으로 정리합니다.
- 다운로드 중에는 최대 60초 동안 삭제를 보류합니다. 삭제·만료 후에는 내용 없는 tombstone을 24시간 보관해 410 응답을 구분합니다.
- **서버가 꺼져 있으면 정리 작업도 멈추며, 남은 파일은 다음 실행 때 정리합니다.** 일반 파일 삭제이며 저장장치 보안 소거를 보장하지 않습니다.

## 지원 범위와 한계

- 단순 디지털 PDF의 텍스트·표·이미지·페이지 크기를 첫 지원 범위로 둡니다. 합성 테스트 통과를 모든 PDF의 품질 보장으로 표현하지 않습니다.
- 스캔·혼합 PDF, 페이지 대부분을 차지하는 이미지(숨은 OCR 레이어 포함)는 `OCR_REQUIRED`로 거부합니다. 이미지 속 일부 글자를 완전히 탐지할 수는 없습니다.
- 암호화 PDF는 사용자 암호 유무와 관계없이 거부합니다. 손상되어 자동 복구가 필요한 PDF, 빈 문서, 100쪽 초과 입력도 명확한 오류를 반환합니다.
- 복잡한 다단, 병합·중첩 표, 부유 이미지, 글꼴 대체, 제목 스타일, 머리말·꼬리말·필드의 정확한 복원은 미검증입니다. `python-docx` 후처리는 문서 개인 속성 정리에만 사용하며 검증되지 않은 레이아웃 재작성은 하지 않습니다.
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
  infrastructure/          # 격리 worker · 안전한 작업 경로
  postprocess/             # python-docx 후처리
  quality/                 # DOCX 텍스트·표·문자 보존 검사
  frontend/                # 한국어 HTML/CSS/JavaScript
scripts/                   # 환경 probe · 합성 PDF 생성
tests/                     # 실제 엔진 및 API 자동 테스트
```

| API | 기능 |
| --- | --- |
| `GET /api/v1/health` | 서버 상태 |
| `GET /api/v1/capabilities` | PDF 엔진·제한·experimental 상태 |
| `GET /api/v1/session` | HttpOnly 세션 쿠키와 CSRF 토큰 |
| `POST /api/v1/jobs` | multipart `file`, `mode=balanced`, `ocr=off`; `X-CSRF-Token` 필요 |
| `GET /api/v1/jobs/{uuid}` | 상태·오류·결과 링크 |
| `GET /api/v1/jobs/{uuid}/download` | DOCX 다운로드 |
| `GET /api/v1/jobs/{uuid}/quality` | 구조 검증 보고서 |
| `DELETE /api/v1/jobs/{uuid}` | 취소·삭제; `X-CSRF-Token` 필요 |

접수는 202로 반환하며, 이후 암호화·OCR·변환 실패는 작업 상태 `failed`와 한국어 오류로 전달합니다. 실패 작업은 다운로드할 수 없습니다.

설계 문서: [PRD](docs/PRD.md), [ARCHITECTURE](docs/ARCHITECTURE.md), [CONVERSION_SPEC](docs/CONVERSION_SPEC.md), [TEST_PLAN](docs/TEST_PLAN.md), [AGENTS](AGENTS.md).

다음 권장 단계는 실문서 corpus·Word 수동 편집 검증, 읽기 순서·표 셀/스타일 품질 평가, 원본/결과 비교와 글꼴 정책 검증입니다. 기능이 달라지는 작업은 별도 Git 브랜치에서 진행합니다.
