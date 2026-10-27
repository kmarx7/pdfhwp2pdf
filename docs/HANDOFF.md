# 개발 단계 마무리 및 인수인계

> 최신 전체 기록: [프로젝트 대화·개발 기록](PROJECT_HISTORY.md). 실행 앱, HWP→PDF, 원본 파일명 유지, 업로드 버튼 개선 및 최신 142개 테스트 결과를 포함한다. 아래는 이전 단계 당시 인수인계다.

> 후속 갱신: 아래는 CLI 단계 당시 기록이다. 2026-10-25 v0.4.0에서 HWP 웹 기본을 native-embedded 경로에 연결했다. 현재 사용법·110개 테스트·실제 웹 결과는 [웹 경로 보고서](NATIVE_WEB_REPORT.md)를 우선한다. 한글 PDF 출력 자체는 수동이다.

2026-10-25. 현재 브랜치 `feat/native-pdf-docx-workflow`. HWP 편집기라는 새 프로젝트로 범위를 넓히지 않고 기존 변환 작업을 정리했다.

## 이번 단계에서 마무리한 기능

- 로컬 FastAPI 및 한국어 PDF/HWP 업로드·진행·오류·DOCX 다운로드 화면
- PDF의 PyMuPDF 분석, pdf2docx 변환, python-docx 후처리와 구조 검사
- HWP 5 직접 변환의 편집용 초안, 표/쪽 번호/일부 배치 힌트 후처리와 한계 안내
- macOS 다운로드 요청 뒤 기본 Downloads 폴더 열기 버튼
- 빈 PDF 글꼴명 회귀 수정과 사용자 선호 native-embedded 경로의 **재현 가능한 로컬 CLI**
- 단계별 보고서, 입력 보존·작업 정리, 실패 시 부분 결과 비공개, 별도 기능 브랜치와 원격 푸시

## 실행

```bash
npm run dev
# 이미 실행한 이 프로젝트의 서버를 갱신할 때
npm run dev -- --restart
# 브라우저: http://127.0.0.1:8000
# 한글 뷰어에서 PDF로 출력한 뒤 사용자 선호 경로 실행
.venv/bin/python scripts/convert_reference_pdf.py reference.pdf runtime/results/native-embedded.docx
```

로컬 서버의 health와 PDF/HWP capabilities 응답을 확인했다. `.venv`와 프로젝트 내부 고정 HWP 엔진만 사용하며 시스템 Python·다른 프로젝트·사용자 글꼴 설치는 변경하지 않았다.

## 검증 결과

`.venv/bin/python -m pytest -q` → **97 passed, 6 warnings in 14.42s**. 전체 회귀 85개와 새 로컬 글꼴 포함/실패 정리 테스트 12개가 통과했다. `node --check app/frontend/static/app.js`, `git diff --check`, `pip check`도 통과했다. 기존 Starlette httpx/SWIG 경고가 남으며 실패나 skip은 없다.

새 글꼴 테스트는 자체 생성한 fixture를 사용한다. 포함 권한 거부, regular/bold 관계, 역난독화한 글꼴 바이트 일치, 본문 불변, 입력·기존 출력 보존, 실패 임시 파일 정리를 검사했다. 실제 기준 PDF에서 CLI 실행도 성공했고, 기존 native-embedded와 본문 XML 및 font alias별 실제 글꼴 데이터가 같았다. [재현 도구 명세](NATIVE_PDF_WORKFLOW.md)

## 결과물과 명확한 한계

사용자가 선호한 기존 결과는 `runtime/layout-review/native-embedded.docx`로 보관한다. 약 52MB이며 Word에서 18쪽으로 표시됐다. 한글/PDF 원본은 16쪽이다. 정식 도구의 재현 결과는 `runtime/deliverables/native-embedded-reproduced.docx`, 보고서는 같은 이름의 `.quality.json`이다. 이 사용자 문서·글꼴 바이너리는 git에서 제외한다. 재생성 가능한 원문 파싱 모델은 마무리 과정에서 삭제했다.

웹앱의 기본 HWP 업로드는 직접 초안 변환이다. **한글 뷰어 PDF 출력은 수동이고, native-embedded 경로는 CLI이며 웹앱에 자동 연결되지 않았다.** 원본 전체 레이아웃 보존 관문과 모든 페이지 Word 시각 비교는 미완료다. 테스트 97개 통과를 이 품질 관문의 완료로 해석하지 않는다. HWPX·OCR·Linux HWP 엔진·Docker 배포·HWP 편집기는 구현하지 않았다.

API 입력·중간 파일은 완료/실패 후 정리하고 성공 결과는 1시간 뒤 만료한다. CLI 저장 결과와 QA 후보·기준 PDF는 자동 TTL 대상이 아니며 수동 삭제 전까지 로컬에 보관한다. 원본 HWP와 사용자 Downloads 파일은 수정/삭제하지 않았다.

후속 범위는 한글 뷰어 PDF 출력의 안정적인 연동 방법, 글꼴 포함 용량, 실제 페이지 차이, 웹앱의 제공 UI를 검증하는 것이다. 이번 단계의 기능 정리와 별개로 품질 미완료 항목을 완료로 표시하지 않는다.
