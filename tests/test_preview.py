from __future__ import annotations

from pathlib import Path

from agentcad.assembly import validate_assembly
from agentcad.preview import check_preview_page, write_model_preview
from agentcad.validate import validate_model
from agentcad.workspace import init_workspace, new_model
from agentcad.jsonio import write_json


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


def test_preview_check_passes_for_model_preview(tmp_path):
    init_workspace(tmp_path)
    new_model(tmp_path, "preview_health")
    result = validate_model(tmp_path, "preview_health")

    health = check_preview_page(Path(result["artifacts"]["preview_page"]))

    assert health["ok"] is True
    assert health["stage"] == "preview-check"
    assert health["kind"] == "model"
    assert health["assets_checked"] >= 2
    assert health["broken_assets"] == []


def test_preview_check_reports_broken_model_asset(tmp_path):
    init_workspace(tmp_path)
    new_model(tmp_path, "broken_asset")
    result = validate_model(tmp_path, "broken_asset")
    preview_page = Path(result["artifacts"]["preview_page"])
    html = preview_page.read_text(encoding="utf-8")
    preview_page.write_text(html.replace('"stlUrl": "broken_asset.stl"', '"stlUrl": "missing.stl"'), encoding="utf-8")

    health = check_preview_page(preview_page)

    assert health["ok"] is False
    assert health["broken_assets"]
    assert health["broken_assets"][0]["kind"] == "component_stl"


def test_preview_check_passes_for_assembly_preview(tmp_path):
    init_workspace(tmp_path)
    new_model(tmp_path, "box")
    root = tmp_path / "assemblies" / "solo"
    root.mkdir(parents=True)
    write_json(root / "assembly.json", {
        "schema": "agentcad.assembly.v1",
        "name": "solo",
        "units": "mm",
        "components": [{"id": "box", "model": "box", "transform": {"translation": [0, 0, 0]}}],
        "mates": [],
        "checks": [],
        "ignore_pairs": [],
    })
    result = validate_assembly(tmp_path, "solo")

    health = check_preview_page(Path(result["artifacts"]["preview_page"]))

    assert health["ok"] is True
    assert health["kind"] == "assembly"
    assert health["broken_assets"] == []
