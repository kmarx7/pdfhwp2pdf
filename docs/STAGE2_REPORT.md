# PDF MVP 구현 및 검증 보고서

검증일: 2026-10-24. 환경: macOS 27.0.1 / Apple Silicon arm64 / 프로젝트 `.venv` Python 3.11.15. 기능 브랜치: `feat/pdf-docx-mvp`.

## 구현 결과

FastAPI와 한국어 HTML/CSS/JavaScript UI에서 PDF 한 개 업로드→유효성 분석→자식 프로세스 변환→DOCX 후처리→구조 검증→다운로드를 구현했다. 외부 서비스·유료 API·DB를 추가하지 않았다. HWP/HWPX 변환 코드는 만들지 않았다.

| 범위 | 실제 구현 |
| --- | --- |
| API | 서버 상태·기능 탐지·세션/CSRF, 업로드·작업 조회·품질 보고서·다운로드·취소/삭제 |
| PDF 분석 | 헤더·파서 열기·손상 복구 여부·암호화·페이지 수·텍스트·이미지·단순 표 분석 |
| 변환 | 독립 `Pdf2DocxEngine`, `ConversionEngine` Protocol, 엔진 등록부/dispatcher, 실제 pdf2docx 호출 |
| 실패 처리 | `ignore_page_error=False`, timeout·RSS·디스크 감시, 실패 작업 다운로드 금지, 한국어 원인·해결 안내 |
| 편집 가능성 | 가시적 텍스트 노드 존재·숨김/극소 글자 거부·문자 집합 99% 보존·과도한 중복 거부, 감지된 표가 있을 때 실제 Word 표 존재 검사 |
| 후처리 | python-docx로 개인 문서 속성 정리·저장. 문단/run/표를 재구성하지 않음 |
| UI | 드롭/파일 선택, 파일명·크기·분석 후 페이지 수, 균형 모드, 실제 단계 표시, 오류·경고·검증 정보·다운로드, 새로고침 후 작업 조회 복원 |
| 파일 관리 | UUID 전용 경로·입력 읽기 전용·원본 hash 보존, 종료 후 입력/중간 파일 삭제, 결과 1시간, tombstone 24시간 |
| 운영 | 단일 서버 저장소 잠금, 동시 변환 1개·대기 5개, 취소 프로세스 종료, 재시작 INTERRUPTED/보관 결과 해시 재검증 |
| 로컬 요청 보호 | Host/Origin·CSRF·업로드 본문/파일 상한·정적 자원 CSP, 원본 파일명을 경로/응답 헤더에 사용하지 않음 |

DOCX는 실제 텍스트·표 개체를 생성한다. 단순 본문 PDF에서 `word/media/`가 없는 것과 표 PDF에서 `w:tbl`·3행 2열·각 셀 내용이 존재하는 것을 검사했다. 스캔 페이지를 이미지로 삽입하는 fallback은 없다. 일부 입력의 문자 레이어만 살려 부분 성공으로 처리하지 않는다.

## 설치와 의존성

일반 pip/uv는 DNS 연결 오류 또는 배포 후보 조회 실패가 발생했다. 공식 PyPI JSON과 wheel을 직접 내려받아 `/tmp` wheelhouse에서 프로젝트 `.venv`에 오프라인 설치했다. 시스템 Python·다른 프로젝트 환경·글꼴·Office 프로그램을 변경하지 않았다.

핵심 확인 버전은 FastAPI 0.162.0, Starlette 1.9.0, Uvicorn 0.54.0, PyMuPDF 1.26.7, pdf2docx 0.5.13, python-docx 1.2.0, pytest 9.1.1이다. `requirements.lock`은 검증 환경의 전체 버전 목록이다. 조사용 olefile과 선택적 문서 QA용 pdf2image도 포함하지만 HWP 엔진이나 앱 렌더링 경로에는 사용하지 않는다.

- [환경·import·합성 smoke 결과](research/stage2-environment.json): exit 0, 영문 합성 PDF→DOCX 문자열 보존·재열기 통과
- [설치 패키지·버전·라이선스 메타데이터](research/stage2-dependencies.json): 배포 메타데이터 기록이며 법적 검토·취약점 감사 완료를 의미하지 않음
- `.venv/bin/python -m pip check`: `No broken requirements found.`

PyMuPDF AGPL/상용 이중 라이선스, pdf2docx 유지보수 중단에 관한 기존 조사 한계는 유지한다. 버전 고정은 보안 업데이트 검토를 대신하지 않는다. Linux·Docker는 아직 실행하지 않았다.

## 자동 테스트 결과

```text
.venv/bin/python -m pytest -q --junitxml=runtime/test-results.xml
38 passed, 6 warnings in 6.28s
```

실패 0, 오류 0, skip 0. [집계 JSON](research/stage2-tests.json)의 JUnit 누적 시간은 6.263초다. 이 시간은 테스트 전체 실행 시간이며 특정 실문서 변환의 성능 보장이 아니다.

| 검사 | 증거 |
| --- | --- |
| 텍스트 PDF 실제 변환 | 영문·한글·다페이지/가로 페이지·이미지 PDF를 별도 프로세스에서 실제 엔진으로 처리 |
| Word 텍스트 개체 | DOCX `w:t` 검사, 단순 본문 문서의 미디어 부재, python-docx 수정/저장/재열기 |
| 표 PDF 처리 | 실제 Word 표 1개, 3행 2열, Item/Amount·Alpha/100·Beta/200 셀 내용 일치, 셀 수정·행 추가 |
| 오류 | 잘못된 PDF·사용자 암호·소유자 암호·스캔·혼합·숨은 OCR 레이어·빈 페이지 문서의 정규화된 실패 |
| 부분 실패 방지 | 엔진 페이지 오류 주입 시 ENGINE_FAILED, 이미지/숨김/누락 텍스트·표 누락 결과의 VALIDATION_FAILED |
| 다운로드 | MIME·고정 파일명 converted.docx·no-store·nosniff·파일 bytes·클라이언트 연결 중단 시 파일/lease 회수 |
| 입력 보호 | 원본 SHA-256 전후 일치, 경로/헤더 공격 파일명 미사용, 빈/비PDF/형식/옵션/초과 크기/다중 파일 거부 |
| 요청 보호 | CSRF·다른 Origin/Host·chunked 본문 상한·잘못된 작업 UUID 검사 |
| 작업 수명 | 큐 상한, 취소·실패 정리, TTL·다운로드 lease·tombstone·재시작·결과 변조·서버 저장소 중복 사용 거부 |
| 자원 | 짧은 deadline·극소 RSS·페이지 수 제한을 주입해 실패·종료·부분 파일 삭제 확인 |

테스트 PDF는 매 실행마다 임시 폴더에 생성한다. 합성 fixture 종류는 정상·한글·표·다페이지·이미지·암호화·스캔 등 12개다. 로컬 수동 시험용은 `scripts/make_test_pdfs.py`로 별도 생성할 수 있다.

경고는 Starlette TestClient의 httpx 사용 중단 예정 안내와 PyMuPDF SWIG 타입의 DeprecationWarning이다. 이번 테스트 실패는 아니며 후속 의존성 갱신 시 대응해야 한다. 경고를 숨기거나 합격으로 바꾸지 않았다.

`node --check app/frontend/static/app.js`와 Python compile 검사를 통과했다.

## 브라우저 확인

`agent-browser`의 독립 로컬 Chrome 세션으로 아래 흐름을 확인했다. 표 PDF의 실제 변환·성공 상태·검증 정보 표시 후 브라우저 `fetch`로 결과 200·DOCX MIME·`attachment; filename="converted.docx"`·37,179 bytes를 확인했다. 암호화 PDF를 선택·변환하면 `PASSWORD_PROTECTED`와 한국어 설명을 표시했다. 브라우저 오류 목록은 비어 있었다.

뷰포트 360px에서 document scrollWidth가 360px로 가로 넘침이 없었으며, 데스크톱/모바일 화면을 직접 확인했다. 실제 업로드에는 절대 경로의 합성 파일을 사용했다. 파일 선택 버튼의 키보드 포커스와 새 작업 시작/기존 작업 삭제 흐름도 확인했다. 모든 접근성 기준의 정식 감사를 수행한 것은 아니다.

- [데스크톱 화면](screenshots/pdf-mvp-desktop.png)
- [모바일 화면](screenshots/pdf-mvp-mobile.png)

## 설계 명세와 현재 구현의 경계

- 1단계 아키텍처의 목표 구조를 유지하되 API는 `app/main.py`, 큐·저장소·정리는 `JobService` 한 모듈에 통합했다. 변환 엔진·분석·후처리·검증·worker·UI는 분리했다.
- 이번 사용자 범위에 맞춰 PDF만 검사한다. HWP/HWPX 파싱·엔진을 만들지 않았고 다른 확장자는 415 `UNSUPPORTED_FORMAT`이다. 초기 계획의 HWP/HWPX 내부 판별은 후속이다.
- 엔진 기능은 `experimental`이다. 사용자의 2단계 지시에 따라 합성 테스트로 실행 기능을 검증했으며, 기존 PRD의 6개 실문서·Word 편집 품질 관문까지 완료한 것은 아니다.
- 제목 레벨/글꼴 대체표/머리말·꼬리말 재구성, `FontResolver`, OCR 엔진, 자체 공통 문서 모델, 시각 비교 렌더러는 구현하지 않았다. pdf2docx가 생성한 서식을 그대로 두고 명확한 한계를 안내한다.
- 문자 보존율은 공백 제거·NFC 이후의 문자 집합 비교다. 원본에서 같은 파서가 놓친 내용, 읽기 순서·문단 의미·표 셀 배치의 오류를 모두 잡아내지 못한다. 실제 CER·SSIM·Word 수동 검사는 `not_measured`/`not_performed`로 표시한다.
- 원본 이미지가 페이지의 85% 이상인 경우 OCR 레이어가 있어도 거부한다. 대형 사진 배경 PDF가 보수적으로 거부될 수 있다. 부분 이미지의 글자·벡터 윤곽선 여부를 완벽히 판정하지는 못한다.
- RSS·디스크 상한은 polling 방식이며 OS 수준 강제 sandbox는 아니다. 갑작스러운 전원 차단, 디스크 고갈·삭제 권한 오류의 모든 조합, live orphan 복구의 모든 경쟁 조건은 미검증이다. symlink 거부·삭제 재시도·프로세스 identity 확인을 구현했지만 공개 멀티테넌트 서비스로 사용하지 않는다.
- DOCX는 구조적으로 수정/저장/재열기했으나 실제 Word 앱 편집·DOCX 렌더링을 수행하지 않았다. 선택된 번들 문서 런타임/LibreOffice 경로를 확보하지 못했고 사용자 설치 Office를 자동 사용하지 않았다. 복잡한 실무 문서와 시각 품질은 미검증으로 남긴다.
- 10쪽/60초 목표의 대표 실문서 성능 측정과 Linux/arm64·amd64 검증은 후속이다.

## 다음 단계 권장

1. 사용권이 있는 한국어·영어 실문서 corpus를 확보하고 Word 편집·저장·재열기와 중요한 숫자·표 내용을 확인한다.
2. 읽기 순서·문단·제목·표 셀/병합·글꼴/페이지 설정 평가를 추가하고 합성·실문서별 지원 범위를 공개한다.
3. 검증된 렌더러·글꼴 환경으로 원본/결과 비교를 구현한다. 비교 이미지를 DOCX 본문 생성에 사용하지 않는다.
4. Linux/Docker 자원 격리·의존성/라이선스 검토를 별도 브랜치에서 수행한다. HWP/HWPX·OCR은 별도 기능 브랜치와 검증 관문으로 진행한다.

실행 명령과 설치·수명 정책은 [README](../README.md)를 따른다. 사용자 요청에 따라 구현·테스트 후 기능 브랜치를 GitHub 원격에 푸시한다.
