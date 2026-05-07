"""Tests for CLI dispatch and auto-init behavior."""
from __future__ import annotations

import json
from pathlib import Path

import agentcad.cli as cli_mod
from agentcad.cli import main


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

    def fake_probe(project_path, model_name, z_values=None, x_values=None, y_values=None, center=None, region=None):
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

    def fake_probe(project_path, model_name, z_values=None, x_values=None, y_values=None, center=None, region=None):
        captured["center"] = center
        return {"ok": True, "stage": "probe", "model": model_name}

    monkeypatch.setattr(cli_mod, "probe_model", fake_probe)
    result = main([
        "probe", "bracket",
        "--z", "1.0", "--center=1,2", "--cx", "3",
    ])
    assert result == 0
    assert captured["center"] == (3.0, 2.0)
