from __future__ import annotations

from pathlib import Path

from agentcad.preview import write_model_preview
from agentcad.validate import validate_model
from agentcad.workspace import init_workspace, new_model


def test_validate_writes_interactive_model_preview(tmp_path):
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
    assert '"stlBase64"' in html


def test_preview_command_fails_before_stl_exists(tmp_path):
    init_workspace(tmp_path)
    new_model(tmp_path, "unbuilt")
    result = write_model_preview(tmp_path, "unbuilt")
    assert result["ok"] is False
    assert result["error"]["type"] == "STLMissing"
