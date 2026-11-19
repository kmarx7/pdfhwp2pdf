"""기준 PDF가 없을 때 변환 버튼 아래에 이유와 다음 행동을 제공하는지 확인한다."""


def test_reference_blocker_markup_is_served(client):
    page = client.get("/").text
    assert 'id="reference-blocker"' in page
    assert 'id="blocker-reference"' in page
    assert 'id="blocker-draft"' in page
    assert 'aria-describedby="engine-notice reference-blocker-text auto-draft-reason"' in page


def test_engine_notice_follows_convert_button_conditions(client):
    script = client.get("/static/app.js").text
    # 버튼 상태를 계산할 때마다 안내도 함께 갱신한다.
    assert "updateEngineNotice();\n}" in script
    assert "!referenceReady()" in script.split("function updateEngineNotice")[1].split("\n}\n")[0]
    # 초안 전환은 사용자가 버튼을 눌렀을 때만 하고 변환을 자동 시작하지 않는다.
    draft_handler = script.split('$("blocker-draft").addEventListener')[1].split("});")[0]
    assert 'switchMode("balanced")' in draft_handler
    assert "convert(" not in draft_handler


def test_new_hwp_without_reference_selects_draft_visibly(client):
    page = client.get("/").text
    script = client.get("/static/app.js").text
    assert 'id="auto-draft-notice"' in page and 'id="auto-draft-reference"' in page
    # 파일을 새로 올릴 때만 초안으로 바꾼다.
    select_file = script.split("async function selectFile")[1].split("\nasync function ")[0]
    assert "updateReferenceStatus({ fallbackToDraft: true })" in select_file
    # 사용자가 직접 모드를 고르면 자동 선택을 해제하고 초안으로 다시 바꾸지 않는다.
    switch_mode = script.split("async function switchMode")[1].split("\n}\n")[0]
    assert "autoDraft = false" in switch_mode
    assert "fallbackToDraft" not in switch_mode
    # 초안 선택은 이유를 화면에 표시하고 변환을 자동 시작하지 않는다.
    fallback = script.split("function useDraftForMissingReference")[1].split("\n}\n")[0]
    assert 'selectedModes.hwp = "balanced"' in fallback
    assert "auto-draft-reason" in fallback
    assert "convert(" not in fallback


def test_reference_pdf_returns_draft_to_embedded_font_mode(client):
    script = client.get("/static/app.js").text
    handler = script.split('$("reference-input").addEventListener("change"')[1].split("\n});")[0]
    assert 'selectedModes.hwp = "native_embedded"' in handler
    assert "autoDraft = false" in handler
