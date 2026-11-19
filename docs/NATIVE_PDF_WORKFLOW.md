# 글꼴 포함 PDF 경유 DOCX 로컬 도구

사용자가 긍정 평가한 `native-embedded` 후보의 재현 경로를 임시 스크립트에서 정식 로컬 CLI로 옮겼다. **한글 뷰어에서 PDF로 저장하는 단계는 수동**이며 웹앱의 HWP 업로드가 이 경로로 자동 연결된 것은 아니다.

## 실행

```bash
.venv/bin/python scripts/convert_reference_pdf.py reference.pdf runtime/results/native-embedded.docx
# 별도 글꼴 폴더 사용 (여러 --font-dir 지정 가능)
.venv/bin/python scripts/convert_reference_pdf.py reference.pdf runtime/results/custom.docx --font-dir /path/to/fonts
```

원본 HWP를 한글 뷰어에서 연 뒤 인쇄 → PDF로 저장해 기준 PDF를 준비한다. 실제 프린터로 인쇄하거나 클라우드에 업로드하지 않는다. CLI는 PDF 분석·pdf2docx 변환·개인 메타데이터 정리·로컬 글꼴 포함·구조 검증을 수행하고 DOCX와 같은 이름의 `.quality.json` 보고서를 만든다. 출력 폴더는 자동 생성한다. 기본 글꼴 폴더는 macOS에 이미 설치된 한글 뷰어의 TTF 폴더와 `~/Library/Fonts`이며, 다른 환경은 `--font-dir`로 명시한다.

## 동작과 제한

- PDF는 30 MiB/100쪽 상한과 기존 보호·OCR/스캔 거부 정책을 적용한다. 페이지 전체 이미지를 DOCX에 넣는 우회를 하지 않는다.
- 문서에 사용된 이름과 로컬 글꼴의 name/OS2 메타데이터를 대응하고 일반·굵은 글꼴을 포함한다. 없는 글꼴은 `FONT_NOT_FOUND`로 실패한다.
- OS/2 `fsType`이 installable 또는 editable embedding을 허용하는 경우만 포함한다. Restricted, Preview/Print, Bitmap-only 또는 알 수 없는 권한 플래그는 `FONT_EMBEDDING_DENIED`로 거부한다. No-subsetting 플래그가 있어도 전체 글꼴을 포함하므로 subset을 만들지 않는다. 이 검사는 플래그 검사이며 별도의 계약이나 모든 배포 상황에 대한 권리 판단을 대체하지 않는다.
- 글꼴 파일·시스템 설정을 설치/변경하지 않는다. 파일당 50 MiB, 포함 합계 200 MiB, 검색 파일 2,000개 상한을 둔다. 글꼴이나 문서 바이너리를 git에 추가하지 않는다.
- DOCX의 본문 XML을 변경하지 않고 fontTable·관계·font part만 추가한다. 글꼴은 GUID 키로 앞 32바이트를 XOR하는 OOXML obfuscated-font 형식이다. [Microsoft의 font part 형식 설명](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oe376/1663dabc-5d98-463f-889e-bcd9b77c3d34)
- 기존 DOCX·보고서를 덮어쓰지 않는다. 출력과 같은 폴더의 전용 임시 디렉터리를 쓰고 성공·실패 후 정리한다. 구조 검증 후 원자적 파일 연결로 결과를 게시한다. 실패하면 이 실행이 만든 부분 결과만 삭제한다. 사용자가 지정한 입력 PDF는 수정하지 않고 전후 SHA-256을 확인한다.
- CLI 결과와 보고서는 사용자가 저장한 파일이므로 수동 삭제 전까지 유지한다. 웹앱 API 결과의 1시간 TTL과 구분한다. 웹앱·DB·외부 API·유료 서비스는 추가하지 않는다.

## 실제 재현 검증

기준 PDF로 정식 CLI를 실행해 `runtime/deliverables/native-embedded-reproduced.docx`를 생성했다. 글꼴 6개, 52,307,128 bytes, 본문 문자 coverage 1.0, Word 표 69개(중첩 포함), 입력 PDF 16쪽을 확인했다. 원본 HWP·기존 다운로드 DOCX·기존 사용자 선호 후보는 덮어쓰지 않았다.

기존 `native-embedded`와 **`word/document.xml`이 바이트 단위로 동일**하고, 각 font alias의 일반/굵은 글꼴 연결을 역난독화한 SHA-256도 전부 같았다. 글꼴 part의 이름·GUID와 개인 메타데이터 등은 달라질 수 있지만, 기준 후보의 본문·표·스타일 지시를 재작성하지 않았다. 이 비교를 새롭게 전체 페이지를 시각 검증한 결과로 표현하지 않는다.

사용자 선호 후보의 실제 Word 표시는 18쪽, 원본 한글/PDF는 16쪽이었다. 원본과 같은 페이지 나눔을 보장하지 않으며 출력 용량·표 분할·글꼴 표시 차이가 남을 수 있다. 이 경로는 사용자 선호 기준을 재현하는 도구이며 전체 HWP 호환성이나 레이아웃 품질 완료 선언이 아니다.
