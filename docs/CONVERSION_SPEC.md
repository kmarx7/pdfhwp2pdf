# 변환 엔진 조사·변환 및 품질 명세

조사 기준일: **2026-10-24**. 공식 저장소·공식 제품 문서·PyPI를 확인했다. 문서상의 지원, 배포 파일 존재, 이 Mac에서의 설치, 실제 문서 품질은 서로 다른 증거다. 이번 단계에서는 실문서를 받지 않았고 실제 변환 품질을 검증하지 않았다.

## 1. 형식별 실현 가능성

| 입력 | 기술적 특성 | 가능한 접근 | 주된 한계 / 현재 결정 |
| --- | --- | --- | --- |
| 디지털 PDF | 글자·그림이 페이지 좌표로 기록됨; 논리적 문단·표 의미가 없거나 불완전할 수 있음 | 글자·선·이미지 분석 → 문단·표 추론 → DOCX | 원본 편집 구조 복원은 추론. 단일 단·단순 표부터 PDF 후보 검증 |
| 스캔/혼합 PDF | 페이지별로 이미지·텍스트 상태가 다름 | 필요한 페이지의 OCR + 레이아웃·표 복원 | OCR 텍스트만 얻어도 표/스타일 복원은 별도. MVP에서는 `OCR_REQUIRED` |
| HWP | v5는 OLE 컨테이너·바이너리 레코드; 구형 변종도 존재 | 네이티브 변환 후보 또는 파서→공통 모델→DOCX | 파싱·HWP 저장이 DOCX 출력은 아님. 기본 비활성 |
| HWPX | ZIP 안의 XML·리소스·스타일 참조 | XML/스타일/컨트롤 해석 → DOCX; 또는 네이티브 후보 | 단순 문자열 추출로는 표·배치 보존 불가. 제한 지원 개발 후보, 기본 비활성 |

## 2. PDF 후보 비교

| 후보 | 실제 범위 | 유지보수·라이선스 근거 | macOS/Apple Silicon | 채택 판단 |
| --- | --- | --- | --- | --- |
| `pdf2docx` | PDF→DOCX API와 표 추출 API 제공. PyMuPDF·python-docx 등에 의존 | PyPI 0.5.13(2026-05-01), Python >=3.10; 공식 저장소는 Artifex 적극 유지보수 중단·MIT 전환 명시 | 본체 py3-none-any wheel; NumPy·OpenCV·PyMuPDF 네이티브 전이 의존성은 별도 검사 필요 | **2단계 첫 실험 후보**. 회귀 코퍼스/버전 고정·격리 어댑터 필수 |
| PyMuPDF + 자체 매핑 + python-docx | PDF 글자·좌표·이미지 분석 및 DOCX 생성 도구를 조합; 완성된 변환 엔진은 직접 개발 | PyMuPDF 공식 릴리스 갱신 확인, AGPL/상용 이중 라이선스. python-docx 1.2.0 MIT | PyMuPDF 1.26.7에 macOS 11+ arm64 abi3 wheel 확인; 실제 import 미확인 | 분석·후처리에 채택. PDF 전체 자체 엔진은 초기 범위 아님 |
| `pdfplumber` + 자체 매핑 | 문자·선·표 추출과 시각 디버깅, DOCX 출력은 별도 | 공식 README Python 3.10~3.14 테스트 명시, MIT | Python 3.11 범위 포함; 로컬 설치·속도 미검증 | 표 인식이 부족할 때 보조 실험; 기본 의존성에 추가하지 않음 |

근거: [pdf2docx 저장소·상태](https://github.com/ArtifexSoftware/pdf2docx), [상태 공지(2026-03-09)](https://github.com/ArtifexSoftware/pdf2docx/discussions/374), [PyPI 버전·Python 요구](https://pypi.org/project/pdf2docx/), [실제 변환 API](https://pdf2docx.readthedocs.io/en/latest/quickstart.convert.html), [의존성](https://raw.githubusercontent.com/ArtifexSoftware/pdf2docx/master/requirements.txt), [PyMuPDF 릴리스](https://github.com/PyMuPDF/PyMuPDF/releases), [PyMuPDF 1.26.7 배포물](https://pypi.org/project/pymupdf/1.26.7/), [python-docx PyPI](https://pypi.org/project/python-docx/), [pdfplumber 공식 README](https://github.com/jsvine/pdfplumber).

`pdf2docx` 최신 소스의 최소 PyMuPDF 요구는 `>=1.26.7`이다. 조사용 조합을 `pdf2docx==0.5.13`, `PyMuPDF==1.26.7`, `python-docx==1.2.0`으로 두되 **호환성 확정 조합은 아니다**. PyMuPDF 최신 문서는 2.0을 다루므로 최소 버전 지정만 믿고 최신 버전으로 자동 업그레이드하지 않는다. 2단계에서 후보의 새 버전·취약점·API 호환을 다시 확인하고 통과 조합의 전이 버전까지 고정한다. [공식 PyMuPDF 문서 및 라이선스](https://pymupdf.readthedocs.io/en/latest/about.html)

## 3. HWP 후보 비교

| 후보 | 실제 지원·출력 | 유지보수/라이선스 확인 | Mac·서버 제약 | 결정 |
| --- | --- | --- | --- | --- |
| `pyhwp` | HWP v5 스트림 분석, 실험적 ODT/TXT 변환. 직접 DOCX 아님, HWPX 대상 아님 | PyPI 최신 0.1b15(2020-05-30), AGPLv3+; Python 3 지원 변경 이력은 있으나 3.11 검증 근거 없음 | lxml·cryptography 등 의존성·오래된 배포 검사 필요; ODT→DOCX는 렌더러 추가 및 이중 손실 | 기본 미채택, 파싱/진단 참고 후보 |
| `hwplib` | Java HWP 읽기·쓰기·구조 접근. DOCX 매핑 별도 | 공식 README 2026-09-11 수정 이력, 1.1.11 Maven 등록(09-09), Apache-2.0 | JDK·Java/Python 경계 추가. arm64 JDK 가능성과 라이브러리 실제 동작은 별도 | HWP 자체 엔진을 만들 경우 파서 후보 |
| `hwp2hwpx` + HWPX 매핑 | HWP→HWPX 중간 변환 라이브러리; DOCX는 다음 단계 필요 | 공식 저장소와 목적 확인; 버전별 지원 커버리지·최근 배포 검증 전 | Java 경로 추가, 두 번의 변환에서 누락 추적 필요 | HWPX 엔진 검증 뒤 보조 실험, 기본 미채택 |
| `pyhwpx` + 한/글 | pywin32/COM으로 설치된 한/글 자동화; 이름이 HWPX라고 순수 XML 라이브러리는 아님 | 공식 README Windows·한/글 설치·Python >=3.9 명시, 공개 릴리스 이력 존재 | macOS/Linux 직접 실행 불가. Office 버전별 DOCX 저장·무인 실행·라이선스는 별도 검증 | 이번 Mac/Linux 기본 아키텍처에서 제외; Windows 확장 가능성만 기록 |
| ONLYOFFICE 로컬 엔진 | 공식 Conversion API 표에 HWP→DOCX 경로가 명시됨 | 공식 8.3 발표에 HWP/HWPX 추가, 현재 API 문서·공개 DocumentServer 저장소 확인. Community 배포 라이선스는 저장소의 AGPL 계열 조건 확인 필요 | Python 패키지가 아님. Desktop·DocumentServer·변환 바이너리의 자동화 인터페이스와 arm64 배포물은 구분해야 함 | **실제 변환 지원이 문서로 확인된 실험 후보**. 설치·자동화·품질 미검증, 현재 활성화/설치 안 함 |
| LibreOffice headless | 공식 안내에서 Hangul WP 97 입력 확인. Writer DOCX 출력과 HWP v5/HWPX 입력 호환은 별개 | 공식 사용자 안내·현재 hwpfilter 소스 확인 | macOS 앱 설치·필터·프로필 격리 필요; 최근 빌드의 v5/HWPX 지원은 이번 근거로 확정 불가 | 범용 HWP v5/HWPX 엔진으로 가정하지 않음. 검증된 ODT→DOCX/렌더링 후보로만 검토 |

근거: [pyhwp 범위](https://github.com/mete0r/pyhwp), [pyhwp 배포·변경 이력](https://pypi.org/project/pyhwp/), [hwplib 공식 저장소](https://github.com/neolord0/hwplib), [hwp2hwpx 공식 저장소](https://github.com/neolord0/hwp2hwpx), [pyhwpx 환경 요구](https://github.com/martiniifun/pyhwpx), [pyhwpx 릴리스](https://github.com/martiniifun/pyhwpx/releases), [ONLYOFFICE 8.3 발표](https://www.onlyoffice.com/blog/2025/02/onlyoffice-docs-8-3-released), [ONLYOFFICE 변환표](https://api.onlyoffice.com/docs/docs-api/additional-api/conversion-api/conversion-tables), [DocumentServer 소스·라이선스](https://github.com/ONLYOFFICE/DocumentServer), [LibreOffice 공식 형식 안내](https://books.libreoffice.org/en/GS75/GS7510-FileFormatsSecurityExporting.html), [현재 hwpfilter 소스](https://github.com/LibreOffice/core/tree/master/hwpfilter).

ONLYOFFICE에서 문서로 확인한 것은 HWP/HWPX→DOCX 변환 경로다. 이 프로젝트의 Python에서 바로 동작하는 함수가 있다는 뜻은 아니다. 실험 시 로컬 실행 방식, 네트워크·파일 전달 방식, 문서 외부 유출 여부, 설치 비용, 부속 서비스와 라이선스를 먼저 기록한다. Community 서버 전체 스택을 MVP 필수 인프라로 자동 도입하지 않는다. 대형 서비스·DB 또는 새 승인 범위를 요구하면 해당 경로를 보류하고 자체 파서 후보를 계속 검토한다.

## 4. HWPX 후보 비교

| 후보 | 확인된 범위 | 유지보수·환경·제약 | 판단 |
| --- | --- | --- | --- |
| Python `zipfile` + 방어 XML 파서 + python-docx | HWPX 패키지와 XML·스타일·표를 직접 해석하고 Word 구조로 매핑해야 함 | 표준 라이브러리 활용 가능; namespace·manifest·스타일 참조·객체 단위 지원 명세와 회귀 테스트 필요 | **제한 지원의 자체 구현 후보**. 이미 지원되는 라이브러리처럼 표현하지 않음 |
| `hwpxlib` | Java HWPX 읽기·쓰기. 직접 DOCX 변환 아님 | 공식 README 2026-08-31 수정 이력, Apache-2.0, 추가 확장 라이브러리 구분. JDK 및 매핑 비용 | 자체 XML 구현의 커버리지가 부족할 때 구조 파서 후보 |
| 한컴 `hwpx-owpml-model` | OWPML 요소 읽기·쓰기 모델과 텍스트 추출 예제; 예제는 첫 섹션 추출 | Apache-2.0. 공식 빌드 안내 Windows 10·Visual Studio 2017·x86; 현재 유지보수 주기 불명 | 형식 참고 근거. Mac용 Python DOCX 엔진으로 채택하지 않음 |
| PyWPDoc | python-docx 기반 DOCX와 HWPX 공통 편집·생성 API | MIT, Python 3.10+, PyPI 프리릴리스 표시. 같은 API로 양쪽 문서를 만드는 예제가 임의 HWPX→DOCX 변환 증거는 아님 | 관찰 후보. 일반 문서 간 서식 변환 엔진으로 간주하지 않음 |
| ONLYOFFICE | HWPX→DOCX 공식 변환표 존재 | HWP 표의 설치·자동화·품질·아키텍처 제약과 동일 | 네이티브 로컬 변환 후보, 비활성 |

근거: [hwpxlib](https://github.com/neolord0/hwpxlib), [한컴 OWPML 모델·빌드 안내](https://github.com/hancom-io/hwpx-owpml-model), [PyWPDoc 공식 README](https://github.com/rydolabs/PyWPDoc), [PyWPDoc PyPI](https://pypi.org/project/pywpdoc/), [ONLYOFFICE 변환표](https://api.onlyoffice.com/docs/docs-api/additional-api/conversion-api/conversion-tables).

결론은 HWP·HWPX 변환이 불가능하다는 뜻이 아니라, 이 프로젝트에서 **검증된 실행 경로가 아직 없다**는 것이다. 텍스트만 추출한 결과로 레이아웃 보존 지원을 선언하지 않는다.

## 5. Apple Silicon·Linux 검토 및 실제 확인 수준

| 항목 | 공식 근거 / 설계 판단 | 이번 로컬 결과 |
| --- | --- | --- |
| Python 3.11 | 프로젝트 `.venv`로 격리 | 3.11.15, arm64, macOS 27.0.1 확인 |
| PyMuPDF 1.26.7 | cp310-abi3 macOS 11+ arm64, manylinux glibc 2.28+ aarch64/x86_64 wheel 확인; CPython 3.11의 후보 | 설치/import 미검증 |
| pdf2docx 0.5.13 | Python >=3.10, 플랫폼 독립 wheel; 전이 네이티브 패키지 확인 필요 | 설치/import 미검증 |
| python-docx 1.2.0 | Python >=3.9; DOCX 생성·편집 지원, 렌더링 기능은 아님 | 설치/import 미검증 |
| FastAPI·Uvicorn·pytest | Python 3.11 기준 설치 후 최소 앱·테스트 확인 예정 | 설치/import 미검증 |
| Java 파서 | arm64 JDK와 실행 경계 필요; 표준 Java라고 전체 호환 보장 안 함 | JDK·패키지 실행 미검증 |
| pyhwpx/COM | Windows 전용 | Mac/Linux 엔진에서 제외 |
| ONLYOFFICE·LibreOffice | 데스크톱 앱의 Mac 지원과 headless 서버/Docker arm64 지원을 별도로 검증 | 설치·실행·버전 미확인 |
| OCR | Tesseract 설치와 `kor`, `eng` traineddata 필요 | 바이너리·언어 데이터 미확인 |
| 한국어 글꼴 | macOS·Linux·Word 설치 글꼴 차이가 줄바꿈에 영향 | 샘플별 글꼴 조사·대체표·렌더링 미검증 |

실제 설치 시도는 셸 DNS 연결 오류로 실패했으며 패키지 미지원으로 결론 내릴 수 없다. 환경 probe는 [environment.json](research/environment.json), 실행 결과는 [TEST_PLAN](TEST_PLAN.md)에 기록한다. Docker는 우선 glibc 기반 Python 3.11 slim 계열을 후보로 두고 이미지 digest·아키텍처별 의존성·글꼴을 검증 후 고정한다. Alpine/musl은 초기 지원 범위로 두지 않는다.

## 6. 판별·변환 규칙

### 파일 식별

- PDF: 헤더와 파서 열기 결과를 함께 확인한다. 암호 필요 여부·페이지 상한·손상 여부를 판정한다.
- HWP: OLE 시그니처만으로 DOC/XLS와 구분하지 않는다. `FileHeader`의 HWP 식별 문자열·버전·플래그와 문서 스트림을 확인한다. HWP v3 같은 구형 입력은 `UNSUPPORTED_VARIANT`; 암호/배포용·제한 문서는 범위에 따라 `PASSWORD_PROTECTED`/`RESTRICTED_DOCUMENT`다.
- HWPX: ZIP 헤더만으로 DOCX와 구분하지 않는다. `mimetype`, `version.xml`, `META-INF`와 콘텐츠 manifest, section/header XML·namespace·참조를 조합해 형식·변종을 판정한다. 구체적인 허용 패키지 변종은 실제 fixture와 공개 형식 명세로 확정한다. 프리뷰 텍스트만 읽어 문서 판별/변환을 완료하지 않는다.
- 확장자와 실제 형식 불일치는 `FORMAT_MISMATCH`로 돌려준다. 상한/압축 폭탄/경로 문제는 ARCHITECTURE의 제한을 파싱 전에 적용한다.

### PDF 처리

1. 페이지의 텍스트·문자 bbox·폰트·이미지·회전·page box·그리기 요소를 분석한다.
2. 텍스트가 없다고 무조건 스캔으로 보지 않는다. 빈 페이지, 도형 위주, 윤곽선 문자, 깨진 ToUnicode 매핑, 이미지 텍스트를 구분하고 불명은 경고한다. 각 페이지의 텍스트 양·읽을 수 없는 문자 비율·이미지 면적을 기록해 OCR 필요성을 판정한다. 임계값은 코퍼스로 보정한다.
3. MVP에서 OCR 필요 페이지가 하나라도 있으면 페이지 번호와 함께 실패시킨다. 문자 레이어가 있는 페이지도 본문 누락·깨진 매핑이 의심되면 무조건 통과시키지 않는다.
4. `pdf2docx` 어댑터로 편집 가능한 본문·표를 생성한다. 단순한 문서부터 검증하며 폰트·그림·복잡한 표가 지원된다고 일괄 보장하지 않는다.
5. 문단·스타일·한글 글꼴·페이지 설정을 필요한 범위에서만 후처리한다. 원래 paragraph/run을 단일 text로 덮어쓰지 않는다. `w:rFonts`의 eastAsia/ASCII 계열을 구분한다.
6. 결과를 구조 검증 후 원자적으로 공개한다. 생성 성공과 품질 목표 달성을 구분한다.

### HWPX 제한 매핑의 개발 순서

본문 section 순서를 manifest로 확인 → header의 font/char/para/style 참조 해결 → run과 문단 → section 페이지 설정 → 단순 Word 표 → 이미지와 관계 → 병합 셀·머리말/꼬리말·필드 순서다. 숫자 순서로 section 파일을 단순 정렬하거나 모든 `t` 태그를 연결하는 방법으로 대체하지 않는다. 본문·표·이미지 등 필수 요소를 읽을 수 없으면 `UNSUPPORTED_FEATURE`로 실패하고 내용을 조용히 버리지 않는다. 경미한 장식 손실은 경고와 정확한 위치를 남긴다. 실제 지원 목록은 4단계 fixture 검증 후 확정한다.

### 공통 서식·이미지·OCR 정책

- 제목 레벨·반복 머리말 추론은 confidence와 근거를 기록한다. 본문 제거가 생길 수 있는 반복 요소 삭제는 코퍼스 검증 후 사용한다. 페이지 숫자를 고정 텍스트에서 Word 필드로 바꿀 때도 자동 확정하지 않는다.
- PDF의 여백은 일반적으로 추론값이다. 원본 section 정보가 있는 HWPX와 구분한다. 같은 크기 페이지마다 section을 불필요하게 늘리지 않되 원본의 강제 나눔은 보존한다.
- 원본 이미지 바이트를 재사용하고 불필요한 리샘플링을 피한다. 클리핑·마스크·벡터 그림은 추가 처리와 경고가 필요하다. 그림만 부분 래스터화할 수 있으나 본문·표를 페이지 이미지로 대체하지 않는다.
- python-docx의 공식 고수준 그림 지원은 인라인 중심이다. 부유 이미지·감싸기·정밀 앵커는 별도 OOXML 매핑과 Word 렌더링 검증 없이는 지원으로 선언하지 않는다. [공식 그림 문서](https://python-docx.readthedocs.io/en/latest/user/shapes.html)
- 글꼴 파일을 자동 추출·재배포·임베딩하지 않는다. 사용 가능한 대체 글꼴은 OS·라이선스·문자 범위를 확인한 설정표로 관리하고 원본/대체 이름을 경고한다. 화면상 유사함과 원본 글꼴 일치를 다른 지표로 측정한다.
- OCR 후보는 로컬 Tesseract `kor+eng`. 텍스트·bbox·confidence를 공통 모델로 넘기고 스캔 페이지를 Word 배경 이미지로 삽입하지 않는다. 사진은 남길 수 있다. OCR에서 원래 글꼴·크기·굵기와 표 구조가 자동 복원된다고 보장하지 않는다. [설치 문서](https://tesseract-ocr.github.io/tessdoc/Installation.html), [언어 데이터](https://tesseract-ocr.github.io/tessdoc/Data-Files-in-different-versions.html)

## 7. 품질 평가 설계

아래 수치는 **제품 목표**이며 현재 측정값이 아니다. 기준 corpus와 사람이 확인한 정답 데이터가 필요하다. 원본 파서 출력을 정답으로 다시 사용하지 않는다. PDF 원본을 만든 편집 문서나 사람이 주석한 텍스트·문단·표·페이지 bbox를 정답으로 보관한다.

### 필수 관문

1. DOCX ZIP·필수 OOXML part·내부 관계가 유효하고 python-docx로 다시 열린다. 이 검사는 전체 OOXML 스키마 적합성이나 Word 정상 열기를 보장하지 않는다.
2. 본문 문자는 `w:p/w:r/w:t` 등 가시적 텍스트로 존재한다. 표는 실제 `w:tbl` 구조이며 주요 표를 이미지·탭 문자열로 대체하지 않는다. 페이지 스크린샷, 숨김 텍스트·폰트 크기 0·백색 숨김 등 편집 가능성 우회는 불합격이다.
3. Word에서 본문 수정, 문단 추가, 표 셀 수정·행 추가, 이미지 이동/크기 변경, 저장·재열기 시 복구 경고 없이 유지된다. 사용자 편집으로 재배치되는 것은 허용하되 원본 변환 직후 읽기 순서와 내용은 보존해야 한다.
4. 원본 파일 해시가 전후 동일하고 필수 본문·표·이미지 누락이 없다. 누락은 점수 평균으로 상쇄하지 않는다.

자동 validator는 1·2의 일부를 검사하고 의심 사항을 경고한다. Word 수동 검증과 4의 정답 대비 검사는 품질 릴리스 관문이며, 런타임 성공만으로 통과했다고 표시하지 않는다.

### 지표·측정 방법·초기 목표

| 지표 | 정의 / 측정 방법 | 단순 디지털 PDF 및 제한 HWPX 목표 |
| --- | --- | --- |
| 문자 오류율 CER | NFC 정규화 후 `(삽입+삭제+치환)/정답 문자 수`. 유의미한 공백·숫자·기호 유지; 정규화 규칙 버전 기록 | 문서별 ≤1%; 금액·날짜·식별자 등 중요 필드 정확 일치 |
| 본문 보존율 | 정답 본문 문자 중 가시적·일반 편집 가능한 텍스트로 매칭된 비율 | ≥99%, 필수 문단 누락 0 |
| 읽기 순서 | 정답 블록 ID 쌍의 순서 중 일치 쌍 비율 | ≥98%; 단일 단 핵심 흐름 역전 0 |
| 문단/제목 F1 | 정답 문자 범위·레벨과 예측 경계의 precision/recall 조화평균; 경계 허용 오차 ±1문자 | 문단 ≥0.95, 제목 ≥0.90 |
| 표 구조 F1 | 정답 셀의 `(행,열,rowspan,colspan)` exact-match 기반 F1, 표는 정답 위치/내용으로 대응 | 단순 표 ≥0.95, 기준 단순 표의 행·열 개수 정확 일치; 셀 텍스트 CER ≤1% |
| 문자 스타일 일치 | 정렬된 문자 구간별 font family/size/bold/italic/color 비교, 크기 오차 ±0.5pt | 크기·굵기 등 ≥95%; 원본 글꼴 존재 시 family ≥95%, 대체율 별도 보고 |
| 페이지 설정 | section 폭·높이 오차와 margin 오차 | 폭·높이 ±1pt; 정답 여백이 있을 때 ±2pt, PDF 추정 여백은 추정 오차 별도 |
| 이미지 보존·위치 | 정답 이미지 목록·hash/시각 대응, 원본 유효 픽셀 수·종횡비, 렌더 bbox | 필수 이미지 보존 100%, 불필요한 다운샘플링 0; 위치 오차 ≤5pt는 렌더 비교 가능 시 측정 |
| 머리말·꼬리말/나눔 | 정답 반복 요소·페이지 경계의 존재·중복·본문 혼입 확인 | 지원 corpus에서 누락/중복 0; balanced의 페이지 수 차이는 보고 |
| 시각 유사도 | 같은 글꼴·렌더러·DPI로 DOCX→PDF→이미지, 원본과 페이지 대응·정렬 후 SSIM 및 bbox IoU | 단순 문서 SSIM ≥0.90 목표, 핵심 블록 중앙 bbox IoU ≥0.85; 글꼴 환경 고정 시만 적용 |

정답/예측 중 한쪽만 표·제목·이미지가 없는 경우를 `해당 없음`으로 처리하지 않는다. 정답 요소가 없고 예측도 없을 때만 해당 없음이다. 빈 텍스트 문서는 CER 분모가 0이므로 `not_applicable`, 예기치 않은 텍스트 생성은 별도 오류다. 미매칭 블록·페이지는 누락/추가로 계산하고, 불리한 페이지를 제외해 평균을 높이지 않는다.

스캔 PDF는 별도 corpus에서 CER ≤5%를 초기 목표로 두고, 숫자·날짜 등 중요 필드 정확도와 표 품질을 따로 측정한다. 복잡한 다단·병합/중첩 표·수식은 탐색군이며 위 MVP 목표 합격군에 섞지 않는다. 탐색군 실패는 공개 제한사항 또는 명확한 미지원 처리로 남긴다.

### 시각 비교·보고서

원본 PDF는 PyMuPDF 등으로 렌더링하고 DOCX는 Word 수동 PDF export 또는 검증한 LibreOffice headless를 이용한다. HWP/HWPX 원본 렌더링이 없으면 작성 도구에서 별도로 export한 기준 PDF를 사용하고 생성 환경을 기록한다. 원본과 결과를 같은 불완전한 변환기로 만들어 자기 일치를 측정하지 않는다.

기준 150 DPI·같은 페이지 크기·렌더러 버전·설치 글꼴 목록을 고정한다. 페이지 수가 다르면 비어 있는 대응 페이지까지 포함하고 텍스트 기반 대응 관계를 표시한다. SSIM만으로 통과시키지 않고 누락·읽기 순서·표 구조·편집성을 함께 검토한다. 비교용 PDF·이미지는 결과 DOCX에 포함하지 않는다.

품질 보고서는 엔진/버전/플랫폼/옵션/입력 해시/처리 시간/지표별 근거/원본 속성의 추정 여부/누락 경고를 남긴다. 자동 보고서에는 문서 원문을 넣지 않는다. 원본 hash는 비공개 작업 보고서에만 두며 운영 로그에는 남기지 않는다. corpus 평가에서는 sample ID·정답 버전·Word 편집 체크 결과·화면 비교·실패 이유를 별도 보관한다.

```json
{
  "schema_version": "1.0",
  "validation_status": "structural_pass",
  "engine": {"id": "pdf2docx", "version": "example"},
  "metrics": {
    "editable_text": {"status": "measured", "value": true, "method": "ooxml_visible_text"},
    "cer": {"status": "not_measured", "value": null, "reason": "ground_truth_missing"},
    "visual_ssim": {"status": "not_measured", "value": null, "reason": "renderer_unavailable"}
  },
  "manual_review": {"word_edit": "not_performed"},
  "warnings": []
}
```

위 JSON은 계약 예시이며 측정 결과가 아니다. 단일 종합 점수는 MVP에서 제공하지 않는다. N/A·미측정값을 100점이나 0점으로 바꾸지 않는다. 전체 corpus 평균 외에도 문서별 값·최솟값·실패 수를 보고하고 필수 관문을 하나라도 실패한 문서를 합격 처리하지 않는다.
