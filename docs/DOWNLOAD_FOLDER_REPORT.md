# 다운로드 폴더 열기

브랜치: `feat/open-downloads-folder`. 로컬 macOS의 변환 성공 화면에서 DOCX 다운로드 요청 후 **다운로드 폴더 열기** 버튼을 표시한다. 기본 `~/Downloads`를 Finder로 연다. PDF/HWP에 공통 적용하며 변환 엔진·파일 정리 정책은 변경하지 않는다.

브라우저의 다운로드 경로와 실제 저장 완료·취소 여부는 알 수 없다. 사용자 지정 저장 폴더를 추정하거나 추가 파일을 저장하지 않으며, 다른 위치로 저장했다면 브라우저 다운로드 목록에서 확인하도록 안내한다. 실패한 변환에는 버튼을 표시하지 않는다. 다른 파일 선택 시 버튼·안내를 초기화한다. 폴더 열기 실패는 변환 성공 상태·다운로드 링크를 유지한 채 별도 안내한다.

`GET /api/v1/capabilities`의 `desktop.open_downloads_folder`로 지원 여부를 알린다. `POST /api/v1/desktop/open-downloads`는 기존 Host/Origin·CSRF 검사를 적용하고 요청 본문을 거부한다. `Desktop` 서비스는 고정된 `/usr/bin/open`과 `Path.home()/Downloads`만 인자 배열로 실행하며 `shell=False`, 5초 제한을 적용한다. 사용자에게 경로를 입력받지 않는다. macOS 이외 환경에서는 기능을 비활성화한다. 공개 서버에서 사용자 컴퓨터 폴더를 여는 기능은 아니다.

오류는 `DESKTOP_UNAVAILABLE`, `DOWNLOADS_FOLDER_MISSING`, `FOLDER_OPEN_FAILED`로 구분하며 경로와 시스템 stderr를 반환하지 않는다. API 성공은 OS 열기 명령 성공을 의미하며 브라우저 파일 저장 완료를 의미하지 않는다.

자동 검증: `.venv/bin/python -m pytest -q` → **77 passed, 6 warnings in 13.79s**. 새 6개 테스트는 CSRF·외부 Origin·임의 경로 거부, 고정된 안전 인자, 미지원 OS·폴더 없음·timeout·실행 실패를 검사했다. 기존 PDF/HWP 변환 테스트를 포함한다. JavaScript 구문 검사도 통과했다.

브라우저 검증: 실행 중인 로컬 서버를 새 코드로 재시작하고 합성 PDF 업로드→변환 성공→다운로드 클릭→폴더 버튼 표시→폴더 열기 API 성공 및 Finder 안내 표시를 확인했다. 화면도 직접 확인했고, 다른 파일 변환 시 버튼과 안내가 숨겨지는 것을 확인했다. 브라우저의 실제 다운로드 저장 경로나 Finder 창의 파일 목록은 검사하지 않았다.
