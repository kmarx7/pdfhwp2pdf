# native-embedded 웹 연결 결과

2026-10-25 · v0.4.0 · `feat/native-web-conversion`

## 변경한 동작

기존 웹앱은 HWP의 직접 DOCX 작성기를 사용했고, 사용자가 선호한 native-embedded는 한글 뷰어 출력 PDF와 글꼴 포함을 사용한 별도 결과였다. 직접 경로는 내용·표를 옮겨도 줄바꿈·글꼴·페이지 배치를 충분히 보존하지 못했다. 따라서 웹 결과와 선호 결과가 달랐다. 이번에는 선호 경로 자체를 웹앱의 새 HWP 기본 모드로 연결했다.

1. 새 HWP를 선택하면 **원본 PDF 기준 · 글꼴 포함**을 선택한다. 이전 직접 초안 작업 복원 후에도 새 파일에서는 기본을 다시 적용한다.
2. `NativeReferences`에 동일 HWP 해시의 유효한 PDF가 있으면 자동 사용한다. 현재 사용자 문서의 전체 출력 PDF 16쪽을 로컬 등록했다. 등록 시점부터 24시간 뒤 만료한다.
3. 없으면 한글 뷰어에서 원본 전체를 PDF로 저장하고 화면의 **기준 PDF 선택**으로 첨부한다. 한글의 PDF 출력 자체는 자동화하지 않았다.
4. 원본/기준 PDF를 분석·대조하고 PDF 전체 페이지를 변환한다. `NativeEmbeddedEngine`은 기존 subset 글꼴명 보정이 적용된 pdf2docx와 로컬 글꼴 포함 모듈을 사용한다. 본문 페이지를 이미지로 넣지 않는다.
5. 구조 검증 뒤 기존 다운로드·검증 정보·다운로드 폴더 열기 흐름을 사용한다. 실패는 실제 오류로 표시하고 직접 초안으로 자동 전환하지 않는다. 직접 초안은 사용자가 별도 선택할 때만 사용한다.

HWP 지원 control을 늘린 작업은 아니다. 기존 보호/미지원 요소 검사와 HWPX·OCR 미지원은 유지한다. 폰트가 없거나 편집 허용 플래그를 확인할 수 없으면 실패한다. 시스템 글꼴 설치·클라우드·유료 API·DB는 추가하지 않았다.

## API·파일·클래스

| 항목 | 계약 |
| --- | --- |
| `POST /api/v1/native/jobs` | CSRF 필요, multipart `file` 한 개와 HWP의 선택적 `reference` PDF 한 개; 나머지 필드 거부. `native_embedded` 고정, 접수 202 |
| `GET /api/v1/native/references/{sha256}` | 같은 HWP의 등록 PDF 존재 여부·쪽 수·만료 시각. 파일 경로 비공개 |
| 작업 조회/삭제/다운로드/품질 | 기존 `/api/v1/jobs/{uuid}` 계약 공유 |
| `NativeReferences` | HWP 해시 결합, PDF 해시 검사, 등록 CLI, 24시간 TTL, 256 MiB 총량 |
| `NativeEmbeddedEngine` | PDF 전체 변환 → 속성 후처리 → 편집 가능한 글꼴 포함 |
| `validate_reference_text` | 정규화 문자 다중집합으로 HWP→기준 PDF 포함률 99% 미만 거부 |
| 격리 worker | 원본 HWP와 기준 PDF 해시 전후 대조, 실제 엔진 ID·글꼴·본문 지표 기록 |

각 입력은 30 MiB/기준 PDF 100쪽까지, 작업은 기존 동시 1개·180초·RSS 1 GiB 제한이다. 글꼴 포함 DOCX는 30 MiB보다 클 수 있다. 입력·중간 파일은 작업 종료 시 삭제하고 실패 부분 결과도 비공개로 삭제한다. 성공 결과는 1시간 보관한다. 첨부 PDF는 작업에만 사용하며 자동 캐시하지 않는다.

등록본은 `runtime/native-references/<HWP SHA-256>/`에 PDF와 내용 없는 메타데이터만 보관한다. 사용/조회로 TTL을 늘리지 않는다. 만료 시 조회 또는 서버 시작/60초 정리에서 삭제하며 서버 중지 시 다음 실행까지 정리가 미뤄진다. QA 기준 PDF·수동 저장한 `runtime/deliverables/` 산출물은 자동 TTL 대상이 아니고 수동 삭제 전까지 로컬에 남는다. 사용자 원본과 기존 Downloads 문서는 수정하지 않았다. `runtime/`·글꼴 파일은 Git에서 제외한다.

## 실제 검증

- `.venv/bin/python -m pytest -q`: **110 passed, 6 warnings**, 실패/skip 없음. 기존 Starlette httpx 및 SWIG 경고다. 기존 97개에 native 웹 경로 13개를 추가했다. 합성 PDF, 자체 생성 글꼴, 공개 Apache Hello World HWP를 사용한다.
- `node --check app/frontend/static/app.js`, `pip check`, `git diff --check` 통과.
- 실제 브라우저에서 사용자 HWP 업로드 → 기준 PDF 16쪽 자동 확인 → 기본 native 모드 변환 성공 → DOCX 다운로드 → 폴더 버튼 표시 → 검증 정보 표시를 확인했다. JS 오류 없음. 390px 모바일에서 긴 파일명과 결과 영역 잘림을 수정하고 다시 확인했다. 초안 선택 뒤 새 HWP를 올리면 native 기본으로 돌아가는 것도 확인했다.
- 브라우저 다운로드 결과: `runtime/deliverables/native-web-browser.docx`, **52,307,132 bytes**, 보고서 `native-web-browser.quality.json`.
- HWP→기준 PDF 본문 문자 포함률 **1.0**, 기준 PDF→DOCX 본문 문자 포함률 **1.0**, 실제 Word 표 **69개**, 포함 글꼴 **6개**. 기준 PDF는 **16쪽** 전체를 처리했다.
- 사용자가 선호한 `runtime/layout-review/native-embedded.docx`와 브라우저 결과의 **`word/document.xml`이 동일**하고, font alias별 regular/bold **8개 관계의 역난독화 글꼴 데이터가 동일**했다. DOCX 파일 해시는 생성 메타데이터와 GUID 때문에 달라질 수 있다.

위 포함률은 문자 다중집합 검사다. 읽기 순서·모든 문단/이미지/도형·시각 배치가 완전히 같다는 뜻은 아니다. 선호 후보의 이전 Word 확인은 원본 16쪽 대비 Word 18쪽이었다. 이번 웹 결과를 Word에서 전 페이지 새로 비교하거나 편집·저장하는 검증은 하지 않았다. 동일 본문/글꼴 재현과 전체 품질 합격을 구분한다.

## 실행과 후속 검증

```bash
npm run dev
# 이미 실행 중인 이 프로젝트 서버의 코드 갱신
npm run dev -- --restart
# http://127.0.0.1:8000

# 같은 HWP의 기준 PDF를 로컬에 24시간 등록할 때
.venv/bin/python scripts/register_native_reference.py /path/to/source.hwp /path/to/reference.pdf
```

다른 HWP에서도 기준 PDF를 준비해 같은 흐름을 사용할 수 있으나 실문서 품질은 개별 확인해야 한다. 다음 검증은 실제 Word 전 페이지 비교/편집, 본문 읽기 순서와 표 셀 대응, 누락 이미지·도형 검사, 글꼴 포함 용량 개선이다. 한글 PDF 출력 자동화는 별도 검증이 필요한 후속 기능이다.
