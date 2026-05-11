"""Tests for CLI dispatch and auto-init behavior."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import agentcad.cli as cli_mod
from agentcad.cli import main


@pytest.fixture(autouse=True)
def _no_serve(monkeypatch):
    monkeypatch.setattr(cli_mod, "serve_preview", lambda *a, **kw: None)
    monkeypatch.setattr(cli_mod, "open_preview", lambda *a, **kw: None)


def test_new_auto_init(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = main(["new", "bracket"])
    assert result == 0
    assert (tmp_path / "bracket" / "cadproject.json").exists()
    assert (tmp_path / "bracket" / "CLAUDE.md").exists()
    assert (tmp_path / "bracket" / "models" / "bracket" / "part.py").exists()


def test_init_creates_workspace_and_optional_model(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = main(["init", "initproj", "--model", "demo"])
    assert result == 0
    project = tmp_path / "initproj"
    assert (project / "cadproject.json").exists()
    assert (project / "models" / "demo" / "part.py").exists()


def test_init_default_creates_project_dir_named_after_model(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = main(["init", "fan8025"])
    assert result == 0
    assert (tmp_path / "fan8025" / "cadproject.json").exists()
    assert (tmp_path / "fan8025" / "models" / "fan8025" / "part.py").exists()


def test_init_model_overrides_workspace_name_for_model(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = main(["init", "fan8025", "--model", "demo"])
    assert result == 0
    assert (tmp_path / "fan8025" / "cadproject.json").exists()
    assert (tmp_path / "fan8025" / "models" / "demo" / "part.py").exists()


def test_new_default_creates_project_dir_named_after_model(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = main(["new", "fan8025"])
    assert result == 0
    assert (tmp_path / "fan8025" / "cadproject.json").exists()
    assert (tmp_path / "fan8025" / "models" / "fan8025" / "part.py").exists()


def test_new_duplicate_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main(["new", "bracket"])
    result = main(["new", "bracket"])
    assert result == 1


def test_new_duplicate_force(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main(["new", "bracket"])
    result = main(["new", "bracket", "--force"])
    assert result == 0


def test_build_missing_model(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main(["new", "bracket"])
    result = main(["build", "nonexistent"])
    assert result == 1


def test_validate_default_model(tmp_path, monkeypatch):
    """Validate the default scaffold model (should build and validate ok)."""
    monkeypatch.chdir(tmp_path)
    main(["new", "test_block"])
    monkeypatch.chdir(tmp_path / "test_block")
    result = main(["validate", "test_block"])
    assert result == 0
    out_dir = tmp_path / "test_block" / "models" / "test_block" / "outputs"
    assert (out_dir / "observability.json").exists()
    validation = json.loads((out_dir / "validation.json").read_text())
    assert validation["artifacts"]["observability"].endswith("observability.json")


def test_version():
    import pytest
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0


def test_sync_updates_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main(["new", "bracket"])
    project = tmp_path / "bracket"
    monkeypatch.chdir(project)

    # Modify a scaffold file
    claude = project / "CLAUDE.md"
    original = claude.read_text()
    claude.write_text("OLD CONTENT")

    # Sync should overwrite it
    result = main(["sync"])
    assert result == 0
    assert claude.read_text() == original

    # Model files should be untouched
    assert (project / "models" / "bracket" / "part.py").exists()


def test_sync_not_a_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = main(["sync"])
    assert result == 1


def test_sync_dry_run_does_not_overwrite(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main(["new", "bracket"])
    project = tmp_path / "bracket"
    monkeypatch.chdir(project)
    claude = project / "CLAUDE.md"
    claude.write_text("LOCAL", encoding="utf-8")

    result = main(["sync", "--dry-run"])
    assert result == 0
    assert claude.read_text(encoding="utf-8") == "LOCAL"


def test_probe_cx_cy_alias(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    main(["new", "bracket"])
    monkeypatch.chdir(tmp_path / "bracket")
    captured = {}

    def fake_probe(project_path, model_name, z_values=None, x_values=None, y_values=None, center=None, region=None, **kwargs):
        captured["center"] = center
        return {"ok": True, "stage": "probe", "model": model_name}

    monkeypatch.setattr(cli_mod, "probe_model", fake_probe)
    result = main([
        "probe", "bracket",
        "--z", "1.0", "--cx", "-10.5", "--cy", "4.25",
    ])
    assert result == 0
    assert captured["center"] == (-10.5, 4.25)


def test_probe_center_and_cx_merge(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    main(["new", "bracket"])
    monkeypatch.chdir(tmp_path / "bracket")
    captured = {}

    def fake_probe(project_path, model_name, z_values=None, x_values=None, y_values=None, center=None, region=None, **kwargs):
        captured["center"] = center
        return {"ok": True, "stage": "probe", "model": model_name}

    monkeypatch.setattr(cli_mod, "probe_model", fake_probe)
    result = main([
        "probe", "bracket",
        "--z", "1.0", "--center=1,2", "--cx", "3",
    ])
    assert result == 0
    assert captured["center"] == (3.0, 2.0)


def test_preview_auto_detects_model(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    main(["new", "bracket"])
    monkeypatch.chdir(tmp_path / "bracket")
    captured = {}

    def fake_model_preview(project_path, target, **kwargs):
        captured["target"] = target
        return {"ok": True, "stage": "preview", "kind": "model", "name": target}

    monkeypatch.setattr(cli_mod, "write_model_preview", fake_model_preview)
    result = main(["preview", "bracket"])

    assert result == 0
    assert captured["target"] == "bracket"


def test_preview_auto_detects_assembly(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    main(["init", "project", "--model", "part"])
    monkeypatch.chdir(tmp_path / "project")
    main(["assembly", "init", "fit"])
    captured = {}

    def fake_assembly_preview(project_path, target, **kwargs):
        captured["target"] = target
        return {"ok": True, "stage": "assembly_preview", "kind": "assembly", "name": target}

    monkeypatch.setattr(cli_mod, "write_assembly_preview", fake_assembly_preview)
    result = main(["preview", "fit"])

    assert result == 0
    assert captured["target"] == "fit"


def test_preview_requires_kind_for_ambiguous_target(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    main(["init", "project", "--model", "shared"])
    monkeypatch.chdir(tmp_path / "project")
    main(["assembly", "init", "shared"])

    result = main(["preview", "shared"])

    assert result == 1


def test_preview_kind_disambiguates_assembly(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    main(["init", "project", "--model", "shared"])
    monkeypatch.chdir(tmp_path / "project")
    main(["assembly", "init", "shared"])
    captured = {}

    def fake_assembly_preview(project_path, target, **kwargs):
        captured["target"] = target
        return {"ok": True, "stage": "assembly_preview", "kind": "assembly", "name": target}

    monkeypatch.setattr(cli_mod, "write_assembly_preview", fake_assembly_preview)
    result = main(["preview", "shared", "--kind", "assembly"])

    assert result == 0
    assert captured["target"] == "shared"


def test_new_variant_with_colon_syntax(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main(["init", "project", "--model", "bracket"])
    monkeypatch.chdir(tmp_path / "project")
    result = main(["new", "bracket:small"])
    assert result == 0
    assert (tmp_path / "project" / "models" / "bracket" / "variants" / "small" / "params.json").exists()


def test_build_variant_with_colon_syntax(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main(["init", "project", "--model", "box"])
    monkeypatch.chdir(tmp_path / "project")
    captured = {}

    def fake_build(project, name, force=False, variant=None):
        captured["name"] = name
        captured["variant"] = variant
        return {"ok": True, "stage": "build", "model": name}

    monkeypatch.setattr(cli_mod, "build_model", fake_build)
    result = main(["build", "box:large"])
    assert result == 0
    assert captured["name"] == "box"
    assert captured["variant"] == "large"


def test_build_without_variant(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main(["init", "project", "--model", "box"])
    monkeypatch.chdir(tmp_path / "project")
    captured = {}

    def fake_build(project, name, force=False, variant=None):
        captured["name"] = name
        captured["variant"] = variant
        return {"ok": True, "stage": "build", "model": name}

    monkeypatch.setattr(cli_mod, "build_model", fake_build)
    result = main(["build", "box"])
    assert result == 0
    assert captured["name"] == "box"
    assert captured["variant"] is None


def test_preview_variant_with_colon_syntax(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main(["init", "project", "--model", "box"])
    monkeypatch.chdir(tmp_path / "project")
    captured = {}

    def fake_model_preview(project_path, target, **kwargs):
        captured["target"] = target
        captured["variant"] = kwargs.get("variant")
        return {"ok": True, "stage": "preview", "kind": "model", "name": target}

    monkeypatch.setattr(cli_mod, "write_model_preview", fake_model_preview)
    result = main(["preview", "box:small"])
    assert result == 0
    assert captured["target"] == "box"
    assert captured["variant"] == "small"


def test_project_flag_resolves_explicitly(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main(["init", "wsp", "--model", "demo"])
    project = tmp_path / "wsp"

    # From a different cwd, --project should find the workspace
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    result = main(["--project", str(project), "build", "demo"])
    assert result == 0


def test_project_flag_rejects_invalid(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = main(["--project", str(tmp_path / "nonexistent"), "build", "x"])
    assert result == 1


def test_preview_static_uses_open_preview(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main(["init", "project", "--model", "box"])
    monkeypatch.chdir(tmp_path / "project")
    opened = {}

    def fake_model_preview(project_path, target, **kwargs):
        return {"ok": True, "stage": "preview", "kind": "model", "name": target,
                "artifacts": {"preview_page": str(tmp_path / "project" / "models" / "box" / "outputs" / "preview.html")}}

    monkeypatch.setattr(cli_mod, "write_model_preview", fake_model_preview)
    monkeypatch.setattr(cli_mod, "open_preview", lambda p: opened.setdefault("path", str(p)))
    monkeypatch.setattr(cli_mod, "serve_preview", lambda *a, **kw: None)

    result = main(["preview", "box", "--static"])
    assert result == 0
    assert "path" in opened
