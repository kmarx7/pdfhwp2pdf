# HWP → PDF 버튼과 실제 엔진 연결

2026-10-27 · v0.5.0 · `feat/hwp-pdf-conversion`

후속 파일명 수정: 아래의 고정 `converted.pdf` 설명은 당시 이력이다. 현재는 원본 basename을 유지하고 확장자만 바꾸며, [README](../README.md)와 [다운로드 규약](ARCHITECTURE.md#다운로드작업-접근)을 우선한다.

## 제공 기능

앱의 변환 유형에 **HWP → PDF 베타**를 추가했다. 파일 선택 → **PDF로 변환하기** → 진행/검증 → **PDF 파일 다운로드** 순서다. 같은 HWP를 선택한 상태에서 Word/PDF 유형을 바꾸면 파일 선택은 유지한다. PDF 모드에서는 Word 글꼴 포함 모드나 기준 PDF 첨부를 요구하지 않는다. 모바일에서 세 유형 버튼을 줄바꿈한다.

설치된 고정 바이너리의 `hwp convert --help`에서 PDF 형식과 `--font-dir` 지원을 직접 확인하고, 실제 `convert --to pdf` 출력을 실행했다. `HwpPdfEngine`은 기존 `HwpCli` 실행·무결성 검사·timeout·자식 프로세스 추적을 사용한다. 새 엔진을 dispatcher에 등록했으며 가상 PDF 변환 함수나 DOCX 이름 변경을 사용하지 않는다. 시스템 앱/패키지·클라우드·DB·외부 유료 API는 추가하지 않았다.

**한글 뷰어에서 출력한 기준 PDF와 다른 렌더러다.** 이 PDF를 native-embedded의 기존 기준 PDF와 동일하다고 표시하거나 자동 캐시에 등록하지 않는다. 원본과 같은 글꼴·표·쪽 나눔은 보장하지 않는다. 기존 HWP 분석기의 암호·배포용·DRM·HWPX·미지원 control 거부를 유지한다.

## API와 파일 계약

| 항목 | 값 |
| --- | --- |
| 접수 | `POST /api/v1/hwp-pdf/jobs`, CSRF 필요, multipart `file` 한 개, 추가 필드 거부 |
| 입력/출력 | HWP 5 한 개 / PDF 한 개, 모드 `hwp_pdf` 고정 |
| 작업 응답 | 입력 `format=hwp`, 출력 `output_format=pdf`; 접수 202 뒤 성공/실패 상태 조회 |
| 엔진 | `hwp-cli-pdf`, 버전 `1.3.1`, experimental |
| 다운로드 | 기존 `/api/v1/jobs/{uuid}/download`, `application/pdf`, 고정 `converted.pdf` |
| 결과 위치 | 작업 `output/result.pdf`, `output/quality.json` |
| 수명/제한 | 입력 30 MiB, 출력 PDF 100쪽, 동시 1개/대기 5개, 180초/RSS 1 GiB/작업 루트 1 GiB, 결과 1시간 |

입력은 읽기 전용 복사본으로 처리한다. 완료·실패·취소 후 입력과 중간 파일을 정리하고 실패 부분 PDF는 제공하지 않는다. 다운로드 lease·만료·삭제·재시작 복구·결과 SHA-256 검사는 DOCX와 공유한다. 이전 작업에 `output_format` 필드가 없으면 DOCX로 해석한다. 사용자 원본은 수정하지 않는다.

## 검증 범위

`PdfQualityValidator`는 생성 PDF 재열기·암호/손상/쪽 수 제한·가시적 텍스트·본문 문자 포함률 ≥99%를 확인한다. 원본에 이미지가 있으면 출력 이미지가 최소 하나 존재해야 한다. 모든 이미지의 개수/픽셀·표 셀 대응·읽기 순서·시각 배치까지 확인하는 검사는 아니다. PDF 개인 메타데이터를 정리한 뒤 검사하고 원본 HWP 해시도 전후 비교한다.

보고서는 `route=hwp_cli_to_pdf`, `output_format=pdf`, `character_coverage`, `output_page_count`, `output_image_count`를 기록한다. 원본 HWP 쪽 수·시각 SSIM은 미측정이다. Word 표 개체 검사 결과로 PDF 품질을 설명하지 않는다.

## 실행 증거

- `.venv/bin/python -m pytest -q` → **126 passed, 6 warnings in 24.33s**, 실패/skip 없음. 기존 110개 + 바탕화면 실행기 4개 + HWP PDF 12개. 경고는 기존 Starlette httpx/SWIG이다.
- 실제 고정 엔진으로 한글·영문 본문, 일반/병합 표, 이미지, 두 구역, 색상 합성 HWP를 변환했다. 본문 포함률 1.0, 다페이지 출력 2쪽과 이미지 존재를 확인했다. 공개 Hello World HWP도 PDF 1쪽과 추출 텍스트를 확인했다.
- API 파일명·PDF MIME·페이지 크기·원본 불변·중간/부분 파일 정리·삭제 후 410·서버 재시작 후 PDF 다운로드를 검사했다. 보호/미지원 요소·잘못된 입력·CSRF 거부 및 누락 텍스트/이미지 실패를 검사했다.
- 브라우저에서 **HWP → PDF → 합성 표 HWP 업로드 → PDF 변환 → 성공 표시 → PDF 다운로드 → 검증 정보**를 확인했다. 내려받은 PDF는 1쪽, 추출 문자 68개, 검출 표 1개였다. JS 오류 없음. Poppler `pdftoppm`으로 브라우저 결과와 합성 이미지 결과를 렌더링해 한글/영문·표·이미지 표시를 확인했다.
- `node --check app/frontend/static/app.js`, `git diff --check` 통과. QA 파일은 `runtime/hwp-pdf-probe/`에 보관하며 Git에서 제외한다. QA 파일은 자동 결과 TTL 대상이 아니다.

이전 사용자 실문서의 알려진 원본 경로는 현재 존재하지 않아 이번 PDF 엔진의 실문서 시각 품질은 확인하지 못했다. 합성 문서 성공을 해당 실문서의 완전한 레이아웃 보존으로 표시하지 않는다. 다음 검증은 사용자 HWP의 한글 출력 PDF와 새 PDF 전 페이지 비교, 표·이미지 대응 및 글꼴 환경별 회귀다.

## 바탕화면 실행 앱

`feat/desktop-launcher`의 구현도 포함한다. Finder로 바탕화면에 **문서잇.app**을 배치하고 아이콘 실행으로 기본 Chrome의 변환 화면이 열리는 것을 확인했다. 이미 실행된 서버는 재사용하며 새 시작·오류/다른 포트 소유자 거부는 자동 테스트로 검사했다. 번들은 현재 프로젝트와 `.venv`를 참조하고 기존 파일을 덮어쓰지 않는다. 로그인 자동 실행은 추가하지 않았다. 브라우저를 닫아도 서버는 백그라운드에 남는다.
