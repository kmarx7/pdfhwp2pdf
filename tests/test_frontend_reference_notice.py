"""기준 PDF가 없을 때 변환 버튼 아래에 이유와 다음 행동을 제공하는지 확인한다."""


def test_reference_blocker_markup_is_served(client):
    page = client.get("/").text
    assert 'id="reference-blocker"' in page
    assert 'id="blocker-reference"' in page
    assert 'id="blocker-draft"' in page
    assert 'aria-describedby="engine-notice reference-blocker-text"' in page


def test_engine_notice_follows_convert_button_conditions(client):
    script = client.get("/static/app.js").text
    # 버튼 상태를 계산할 때마다 안내도 함께 갱신한다.
    assert "updateEngineNotice();\n}" in script
    assert "!referenceReady()" in script.split("function updateEngineNotice")[1].split("\n}\n")[0]
    # 초안 전환은 사용자가 버튼을 눌렀을 때만 하고 변환을 자동 시작하지 않는다.
    draft_handler = script.split('$("blocker-draft").addEventListener')[1].split("});")[0]
    assert 'switchMode("balanced")' in draft_handler
    assert "convert(" not in draft_handler
