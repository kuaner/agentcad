from __future__ import annotations

from pathlib import Path

from agentcad.validate import deliver_model
from agentcad.workspace import init_workspace, new_model


def test_deliver_includes_only_existing_artifacts(tmp_path: Path, monkeypatch):
    init_workspace(tmp_path)
    new_model(tmp_path, "m")
    out_dir = tmp_path / "models" / "m" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "m.step").write_text("x", encoding="utf-8")
    (out_dir / "preview.back.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path / "models" / "m" / "metadata.json").write_text("{}", encoding="utf-8")

    def fake_validate(project, name, render_view="iso", render_views=None):
        return {"ok": True, "stage": "validate"}

    monkeypatch.setattr("agentcad.validate.validate_model", fake_validate)
    result = deliver_model(tmp_path, "m", run_validation=True)
    artifacts = result["artifacts"]
    assert "step" in artifacts
    assert "stl" not in artifacts
    assert "preview_back" in artifacts
    assert "metadata" in artifacts
    assert "deliverable" in artifacts
