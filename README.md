# PDF·HWP·HWPX → DOCX

원본의 텍스트·문단·표·이미지·서식을 최대한 보존해 편집 가능한 Word 문서를 만드는 로컬 웹앱 프로젝트입니다. 페이지 전체를 이미지로 삽입하는 변환은 제공하지 않습니다.

## 현재 상태

2026-10-24 기준 **1단계 조사·설계 완료**입니다. 웹앱과 변환 엔진은 아직 구현하지 않았습니다. 아래의 폴더·클래스·API는 구현 명세이며 실행 가능한 서비스가 아닙니다.

| 구분 | 결정과 상태 |
| --- | --- |
| 실행 환경 | 프로젝트 `.venv`, Python 3.11 우선; 로컬 3.11.15 / macOS 27.0.1 / arm64 확인 |
| 애플리케이션 | FastAPI, HTML5/CSS3/JavaScript, 단일 서버·파일 기반 작업 저장소 설계 |
| PDF | PyMuPDF 분석 + `pdf2docx` 후보 어댑터 + `python-docx` 후처리; 설치·변환 미검증 |
| HWP | 기본 비활성. ONLYOFFICE 로컬 변환 경로와 `hwplib` 기반 자체 매핑을 조사 후보로 유지 |
| HWPX | 기본 비활성. 제한된 XML→공통 모델→DOCX 구현과 ONLYOFFICE 경로를 비교 검증 예정 |
| OCR | 교체 가능한 인터페이스만 설계; Tesseract 로컬 처리 후속 단계 |
| 품질 | 편집 가능성 필수 조건 + 구조·텍스트·시각 지표 + Word 수동 편집 검증 |

`pdf2docx`는 Artifex의 적극적인 유지보수가 중단되어 격리·버전 고정이 필요합니다. [공식 상태 공지](https://github.com/ArtifexSoftware/pdf2docx/discussions/374)
HWP·HWPX→DOCX는 [ONLYOFFICE 공식 변환표](https://api.onlyoffice.com/docs/docs-api/additional-api/conversion-api/conversion-tables)에 기재되어 있으나 이 프로젝트에서 실행하거나 품질을 확인한 것은 아닙니다.

## 문서 안내

- [PRD](docs/PRD.md): 요구사항, MVP, 개발 순서와 완료 기준
- [ARCHITECTURE](docs/ARCHITECTURE.md): 모듈, 폴더·클래스 구조, API, 작업·파일 수명
- [CONVERSION_SPEC](docs/CONVERSION_SPEC.md): 형식별 엔진 비교, 출처, 변환 규칙, 품질 평가
- [TEST_PLAN](docs/TEST_PLAN.md): 테스트 행렬, 합격 기준, 이번 실행 결과
- [AGENTS](AGENTS.md): 다음 개발 작업에서 지킬 규칙

## 기술 검증 재현

이미 프로젝트 전용 `.venv`를 만들었습니다. 시스템 Python이나 다른 프로젝트의 패키지를 변경하지 않았습니다.

```bash
# 다른 체크아웃에서 환경을 새로 만들 때만 실행
python3.11 -m venv .venv

# 외부 패키지 없이 환경·설치 상태 확인
.venv/bin/python scripts/probe_environment.py

# 네트워크 사용이 가능한 환경에서 설치 후보 확인
.venv/bin/python -m pip install --no-cache-dir -r requirements-probe.txt
.venv/bin/python scripts/probe_environment.py --smoke
```

`requirements-probe.txt`는 조사용 후보 목록이며 운영 lock 파일이 아닙니다. PDF 후보 3개 버전만 고정했고 나머지·전이 의존성은 설치 검증 후 lock으로 확정합니다. 이전 버전 고정은 취약점 검토를 대신하지 않습니다.

이번 설치 시도는 `Failed to establish a new connection: [Errno 8] nodename nor servname provided, or not known`으로 실패했습니다. 이는 패키지의 Apple Silicon 미지원 판정이 아닙니다. FastAPI·PyMuPDF·python-docx·pdf2docx·pytest 설치 및 import는 확인되지 않았습니다.

검증 스크립트는 의존성 부족 시 종료 코드 `2`, smoke 실패 시 `1`, 성공 시 `0`을 반환합니다. `--smoke`는 설치된 PDF 후보로 자동 생성한 한 페이지 영문 PDF의 텍스트가 DOCX에 남는지만 검사합니다. 실제 한국어 문서·표·레이아웃 품질 검증을 대신하지 않습니다. 임시 생성 파일은 실행 종료 시 삭제합니다. 이번에는 의존성이 없어 smoke를 실행하지 못했습니다. 실제 측정 결과는 [환경 기록](docs/research/environment.json)에 있습니다.

## 다음 단계

2단계는 의존성 설치·고정, PDF용 최소 변환 경로, 파일 판별·안전한 업로드, 작업 조회·다운로드, 한국어 UI와 오류 처리, pytest 및 실제 샘플 검증입니다. HWP/HWPX는 판별·명확한 미지원 응답까지 포함하고 실제 엔진 활성화는 별도 품질 관문을 통과한 뒤 진행합니다. 로컬 웹서버 실행 명령은 앱 구현 후 추가합니다.

클라우드 서비스·유료 API·데이터베이스는 추가하지 않았습니다. PyMuPDF의 AGPL/상용 이중 라이선스와 배포 방식은 공개 배포 전에 검토해야 하며, 유료 계약을 선택한 것은 아닙니다. [공식 라이선스](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright)
