from __future__ import annotations

from pathlib import Path

from agentcad.preview import write_model_preview
from agentcad.validate import validate_model
from agentcad.workspace import init_workspace, new_model


def test_validate_writes_live_model_preview(tmp_path):
    init_workspace(tmp_path)
    new_model(tmp_path, "preview_block")

    result = validate_model(tmp_path, "preview_block")
    assert result["ok"] is True
    preview_page = Path(result["artifacts"]["preview_page"])
    assert preview_page.exists()
    html = preview_page.read_text(encoding="utf-8")
    assert "three.module.js" in html
    assert "STLLoader" in html
    assert '"kind": "model"' in html
    assert '"stlUrl"' in html
    assert '"mode": "fetch-relative-url"' in html
    assert '"validation": "validation.json"' in html
    assert 'id="explode"' in html
    assert 'id="next-part"' in html


def test_preview_command_fails_before_stl_exists(tmp_path):
    init_workspace(tmp_path)
    new_model(tmp_path, "unbuilt")
    result = write_model_preview(tmp_path, "unbuilt")
    assert result["ok"] is False
    assert result["error"]["type"] == "STLMissing"


def test_preview_escapes_script_payload_separators(tmp_path):
    init_workspace(tmp_path)
    new_model(tmp_path, "unicode_case")

    result = validate_model(tmp_path, "unicode_case")

    assert result["ok"] is True
    html = Path(result["artifacts"]["preview_page"]).read_text(encoding="utf-8")
    assert "\\u2028" not in html

    injected = write_model_preview(
        tmp_path,
        "unicode_case",
        validation_payload={
            "ok": True,
            "stage": "validate",
            "checks": [{"name": "line\u2028sep", "type": "script\u2029safe", "ok": True}],
            "artifacts": {},
        },
    )
    assert injected["ok"] is True
    html = Path(injected["artifacts"]["preview_page"]).read_text(encoding="utf-8")
    assert "\\u2028" in html
    assert "\\u2029" in html
    assert "line\u2028sep" not in html
