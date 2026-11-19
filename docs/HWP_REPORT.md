# HWP 5 → DOCX 베타 구현 및 검증

검증일: 2026-10-24. 브랜치: `feat/hwp-docx`. 환경: macOS 27.0.1 / Apple Silicon arm64 / 프로젝트 `.venv` Python 3.11.15.

## 구현 결과

기존 PDF 변환 흐름에 **HWP 5 바이너리 문서의 실제 DOCX 출력**을 추가했다. 화면에서 `HWP → Word 베타`를 선택하거나 HWP를 드롭하면 HWP 엔진을 사용한다. 결과는 텍스트·표·이미지의 Word 개체이며 HWP를 페이지 이미지나 PDF로 바꾸는 중간 경로를 사용하지 않는다.

| 모듈 | 역할 |
| --- | --- |
| `FileTypeDetector` | PDF/OLE/HWP 3 헤더 구별, 확장자 위장 거부. OLE 전체를 HWP로 가정하지 않고 다음 분석에서 FileHeader 확인 |
| `HwpAnalyzer` | OLE의 실제 HWP5 서명·버전·보호 플래그, 내부/압축 크기 상한, IR 분석과 미지원 요소 거부 |
| `HwpCli` | 고정 native 실행 파일 해시 확인, 인자 배열·전용 cwd·60초 호출 제한, 소유 native PID 이벤트 전달 |
| `HwpCliEngine` | HWP 5→DOCX 실제 호출. 공통 `ConversionEngine` 계약을 통해 등록·선택 |
| `HwpDocxPostProcessor` | 기존 본문·셀·병합을 유지하며 원본 열 너비·기본 테두리·배경·셀 여백 복원 |
| `QualityValidator` | 문자 보존, 표 수·행/열·병합·열 치수, 이미지 원본 바이트 SHA-256, 섹션 수·페이지 크기 검사 |
| 기존 supervisor | native 자식까지 같은 프로세스 그룹으로 종료, 전달받은 PID/생성 시각으로 RSS 합산, 실패 부분 파일 정리 |

Mac 제한 환경에서는 전체 프로세스 열거가 거부될 수 있어 `psutil.children()`을 사용하지 않는다. worker가 직접 시작한 native 프로세스의 PID/생성 시각만 감독자에게 전달한다. 부모 API가 사라지면 세션 리더인 worker가 자기 작업 프로세스 그룹을 종료한다. OS 수준 sandbox나 정확한 순간 최대 RSS 측정을 보장하는 것은 아니다.

## 엔진 선택과 설치

`STAIxBWLB/hwp-cli` **v1.3.1** 공식 macOS arm64 배포물을 선택했다. 직접 DOCX export, 전체 JSON IR, HWP 바이너리 생성 기능을 실제 실행했다. 기존 조사 이후 확인한 후보이며 작은 새 프로젝트이므로 `experimental` 상태를 유지한다. 상용 프로그램·Java·Windows COM·DB·외부 변환 API를 도입하지 않았다. [공식 저장소](https://github.com/STAIxBWLB/hwp-cli), [고정 릴리스](https://github.com/STAIxBWLB/hwp-cli/releases/tag/v1.3.1)

배포 아카이브 8,950,463 bytes를 내려받아 공식 SHA-256과 대조했다. 실행 파일도 별도 SHA-256으로 고정했다. 설치 위치는 `.tools/hwp-cli/1.3.1/`이며 git에서 제외한다. 설치 스크립트는 예상된 4개 일반 파일만 추출하고 경로 탈출·링크·크기·해시를 확인한다. 전역 환경이나 사용자 Office/글꼴 설치는 변경하지 않는다. [설치 원자료](research/hwp-engine.json)

```bash
.venv/bin/python scripts/install_hwp_engine.py
# 공식 배포 파일을 미리 받은 경우
.venv/bin/python scripts/install_hwp_engine.py --archive /path/to/hwp-v1.3.1-aarch64-apple-darwin.tar.gz
npm run dev -- --restart
```

기존 `.tools` 설치에서 로컬 아카이브를 통한 설치 확인과 CLI `hwp 1.3.1` 실행을 확인했다. HWP 설치가 없거나 파일 해시가 다르면 API는 unavailable을 표시하고 HWP 변환을 활성화하지 않는다. PDF는 독립적으로 사용할 수 있다. Linux/Intel HWP 배포물은 이번에 활성화하거나 검증하지 않았다.

엔진은 MIT OR Apache-2.0이며 [라이선스·NOTICE](../third_party/hwp-cli/NOTICE)를 보관했다. 독립 HWP fixture의 Apache-2.0 라이선스·출처·해시도 [fixture 안내](../tests/fixtures/hwp/README.md)에 기록했다.

## 발견한 한계와 보완

고정 릴리스의 DOCX writer는 내용 중심 export이며 페이지 레이아웃 복원 엔진이 아니다. 특히 다음을 확인했다. [고정 DOCX writer 소스](https://github.com/STAIxBWLB/hwp-cli/blob/v1.3.1/crates/hwp-convert/src/docx.rs)

- `convert --strict`/손실 ledger는 HWP/HWPX 출력에만 적용되고 DOCX에는 적용되지 않는다. 이를 품질 보장으로 사용하지 않고 자체 분석기에서 미지원 control·알 수 없는 본문 record를 거부한다.
- 기본 writer가 표 열 너비를 균등하게 만든다. 원본 셀의 `(열, 열 병합 수, 너비)` 제약으로 열 경계를 복원하고 DOCX의 grid/cell/table 너비를 보정했다. 원본 셀 내용이나 run을 재작성하지 않는다.
- 기본 writer가 테두리를 검은 실선으로 만든다. 원본의 선 없음/단일 실선·색·두께와 단색 배경·셀 여백을 후처리했다. 복잡한 선·그라데이션/그림 채움은 조용히 대체하지 않고 거부한다.
- 머리말·꼬리말이 생략되고 수식은 script text로 대체될 수 있다. 현재 이 기능들을 포함한 문서는 원본 내용을 누락시키지 않도록 실패시킨다.

HWP 페이지 수는 파싱만으로 확정할 수 없어 API에서 `null`, UI에서 `페이지 수는 측정하지 않음`으로 표시한다. 섹션 크기와 페이지 수는 다른 개념이다.

## 자동 테스트 결과

```text
.venv/bin/python -m pytest -q --junitxml=runtime/hwp-test-results.xml
57 passed, 6 warnings in 11.33s
```

실패 0 / 오류 0 / skip 0. 기존 PDF·작업 관리 테스트 38개와 HWP 테스트 19개가 함께 통과했다. [집계 JSON](research/hwp-tests.json)

| 검증 범위 | 확인한 내용 |
| --- | --- |
| 실제 HWP 출력 | 한글/영문 본문, Arial 18pt·굵게·색상 `112233`가 실제 `w:t`/run 속성에 존재 |
| 일반 표 | 3행 2열·한글 셀 내용 일치, 40mm/110mm의 비균등 열 너비 보존 |
| 병합 표 | 세로 2행 병합과 가로 2열 병합 유지, 실제 Word 셀 개체로 존재 |
| 이미지 | 원본 바이트 hash 동일, Word 인라인 이미지 존재·개수 일치 |
| 여러 섹션 | 2개 섹션과 각각의 본문·페이지 크기 유지. 실제 페이지 수와 동일하다고 주장하지 않음 |
| 독립 입력 | Apache-2.0의 hahnlee/hwp-rs `hello_world.hwp`를 변환해 예상 본문 `Hello World!` 확인 |
| 편집 개체 | python-docx로 본문·셀 수정 및 저장·재열기. 실제 Word 앱 수동 편집과 구분 |
| 실패/보호 | 잘못된 OLE/HWP·확장자 위장·HWP 3·보호 플래그·머리말 미지원 거부, 실패 DOCX 다운로드 금지 |
| 무결성 | 원본 hash 동일, 결과 표/이미지 손실 주입 거부, 다른 실행 파일·잘못된 설치 아카이브 거부 |
| 수명/회귀 | 기존 큐·취소·timeout·RSS·삭제·TTL·재시작·다운로드·PDF 테스트 유지 |

합성 HWP는 `scripts/make_test_hwps.py`가 본문·표·병합·이미지·섹션·머리말·단색 배경 표 7종과 보호 플래그 3종을 생성한다. HWPX는 이 테스트 입력을 작성하는 중간 파일일 뿐이며 앱 입력으로 지원하지 않는다. 보호 플래그 3종은 **실제 암호 알고리즘을 적용한 문서가 아니라** 거부 경로 확인용이다. 실제 암호화/DRM 변종 전체 검증은 남아 있다.

경고 6개는 기존 Starlette TestClient httpx 사용 중단 예정 안내 및 PyMuPDF SWIG DeprecationWarning이다. `pip check`, JavaScript 구문, Python 구문도 확인했다.

## 브라우저 검증

실행 중이던 PDF 전용 서버를 프로젝트 경로·실행 명령을 확인한 뒤 새 0.3.0 서버로 재시작했다. 다른 프로그램이 8000번 포트를 사용하면 재시작 도구가 종료를 거부한다.

독립 Chrome 세션에서 `HWP → Word 베타` 선택→실제 합성 표 HWP 업로드→성공 상태→다운로드 응답을 확인했다. 응답은 200, DOCX MIME, `attachment; filename="converted.docx"`, 3,770 bytes였다. 미지원 머리말 문서는 `UNSUPPORTED_FEATURE`와 한국어 원인으로 중단되고 다운로드가 숨겨졌다. 브라우저 오류 목록은 비어 있었다.

360px에서 document scrollWidth 360px로 가로 넘침이 없었고 양쪽 화면을 직접 확인했다. [데스크톱](screenshots/hwp-mvp-desktop.png), [모바일](screenshots/hwp-mvp-mobile.png)

## 남은 품질 범위

실제 Microsoft Word 앱의 열기·편집·렌더링 비교, 한국어 실무 HWP 5개 이상의 정답 corpus, 정확한 읽기 순서·문단/제목 레벨·시각 점수는 미검증이다. 한 개 독립 문서와 합성 입력 성공을 전체 HWP 품질 관문 통과로 표현하지 않는다.

HWP 3, HWPX, 보호 문서, 머리말·꼬리말·필드·수식·도형·각주·다단, 알 수 없는 본문 요소, 복잡한 표 장식은 현재 지원 범위 밖이다. 부유 배치·정확한 페이지 나눔·이미지 회전/자르기·글꼴 대체·자동 번호·페이지 장식은 동일성을 보장하지 않는다. 입력 원본 보존과 결과 1시간 수명 정책은 PDF와 동일하다.

다음 단계는 사용자 실문서로 Word 편집·읽기 순서·표/서식 품질을 검증하고, 빈도가 높은 미지원 요소부터 별도 브랜치에서 추가하는 것이다. HWPX 및 Linux 지원도 별도 기능·플랫폼 관문으로 진행한다.

## 후속 오류 진단 개선

`fix/hwp-error-details`에서 실제 실패 작업의 `details.features = ["pgnp"]`를 확인했다. 이는 쪽 번호 위치 설정이며, 엔진의 [구조 매핑 문서](https://github.com/STAIxBWLB/hwp-cli/blob/main/docs/design/11-hwpx-structure-map.md)에서도 `pageNum`과 연결된다. 기존 화면은 감지된 요소와 관계없이 머리말·꼬리말 등 전체 미지원 예시를 보여 줬다.

분석 오류에 실제 감지 요소의 한국어 이름을 추가했고, 화면은 기존에 저장된 `pgnp` 오류도 정확하게 설명한다. 실패 후 하단 안내가 변환 시작을 권하는 문제도 수정했다. 미지원 요소 거부 정책은 유지하며 쪽 번호 지원을 추가한 것은 아니다. 작업 원본 사본은 실패 정리 정책에 따라 남아 있지 않아 사용자 문서 재변환은 미검증이다.

검증: `.venv/bin/python -m pytest -q` → **59 passed, 6 warnings in 12.85s**. 쪽 번호 및 알 수 없는 요소의 오류와 실제 머리말 입력의 API 오류를 검사했다. `node --check` 통과. 독립 브라우저에서 기존 형식의 `pgnp` 오류 객체로 새 안내 표시를 확인했다. 이는 사용자 원본의 변환 성공 검증이 아니다.

## 후속 쪽 번호 변환 지원

브랜치 `feat/hwp-page-numbers`에서 제한된 `pgnp` 지원을 추가했다. 기존에는 모두 거부했지만, 이제 지원 범위의 쪽 번호는 삭제하지 않고 Word 자동 `PAGE` 필드로 복원한다. UI에도 필드 업데이트 안내를 표시한다. 오류 안내만 바꿨던 직전 수정과 구분한다.

근거는 고정 v1.3.1의 [pgnp 파서](https://github.com/STAIxBWLB/hwp-cli/blob/v1.3.1/crates/hwp-render/src/page_number.rs), [위치 매핑](https://github.com/STAIxBWLB/hwp-cli/blob/v1.3.1/crates/hwpx/src/read/section.rs), [구역 간 유지 및 문서 시작 번호 처리](https://github.com/STAIxBWLB/hwp-cli/blob/v1.3.1/crates/hwp-render/src/layout.rs)다. `Generic.data`의 12바이트를 `<I4H`로 해석하며 숫자 형식·위치·장식 문자를 검증한다.

| 항목 | 지원·처리 |
| --- | --- |
| 배치 | 구역 시작의 위/아래 × 왼쪽/가운데/오른쪽 6종, 번호 없음 설정 |
| 번호 모양 | 아라비아 숫자, 대/소 로마 숫자, 대/소 영문자. 지원하지 않는 모양을 숫자로 임의 대체하지 않음 |
| 장식 | 앞·뒤 WCHAR와 양쪽 장식 문자. XML 제어 문자·surrogate는 거부 |
| 시작·연속 | 문서 `start_numbers[0]`, 다음 구역으로 설정 유지, 번호 없음 전환. 각 구역의 header/footer 참조를 분리해 원치 않는 번호 연결을 차단 |
| DOCX | 위치에 맞는 header/footer, 문단 정렬, `w:fldSimple`의 PAGE 명령, `w:pgNumType`, `w:updateFields` 및 dirty 플래그 |
| 검증 | PAGE 필드 개수·위치·숫자 형식·정렬·장식·시작 번호 검사. 필드 제거를 주입하면 결과 거부 |
| 계속 거부 | 본문 중간의 설정 변경, 표 내부 설정, 안쪽/바깥쪽 교대 배치, 원문자·사용자 지정 숫자, pghd/nwno/pgct 등 별도 쪽 제어, 미해석 payload/자식 레코드 |

이 기능은 일반 머리말·꼬리말 콘텐츠 지원을 뜻하지 않는다. 숫자 결과 캐시는 저장하지 않으며 Word가 PAGE를 계산하도록 요청한다. 필드를 계산하지 않는 미리보기는 번호를 빈칸으로 보일 수 있다. 실제 Word GUI에서 필드 업데이트·번호 표시·페이지 나눔·쪽 번호 글꼴은 **미검증**이다. 원본 페이지 수와 결과의 같은 페이지 번호를 보장하지 않는다.

테스트 입력은 실제 바이너리 HWP 4종을 추가 생성했다: 아래 가운데 `- PAGE -`, 위 오른쪽 로마 숫자 및 시작 번호 4, 두 구역에서 번호 해제, 두 구역에서 번호 유지. 합성 입력은 총 14종이며 원래 업무 문서를 git에 추가하지 않았다.

전체 자동 테스트: `.venv/bin/python -m pytest -q` → **71 passed, 6 warnings in 14.55s** (PDF/공통 38 + HWP 33). `node --check` 통과. 실행 중인 로컬 앱에서 합성 `page_numbers.hwp` 업로드 → 성공 화면 → DOCX 다운로드 응답 200/MIME/4,711 bytes를 확인했다. 사용자 스크린샷의 원본 파일은 제공되지 않아 해당 문서의 성공을 확인한 것은 아니다. 새로 업로드하면 새 코드로 분석하며, 기존 실패 작업의 상태를 성공으로 바꾸지 않는다.
