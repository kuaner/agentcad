"""Tests for CLI dispatch and auto-init behavior."""
from __future__ import annotations

import json
from pathlib import Path

import agentcad.cli as cli_mod
from agentcad.cli import main


def test_new_auto_init(tmp_path):
    result = main(["new", "--project", str(tmp_path / "newproject"), "bracket"])
    assert result == 0
    assert (tmp_path / "newproject" / "cadproject.json").exists()
    assert (tmp_path / "newproject" / "CLAUDE.md").exists()
    assert (tmp_path / "newproject" / "models" / "bracket" / "part.py").exists()


def test_init_creates_workspace_and_optional_model(tmp_path):
    project = tmp_path / "initproj"
    result = main(["init", "--project", str(project), "--model", "demo"])
    assert result == 0
    assert (project / "cadproject.json").exists()
    assert (project / "models" / "demo" / "part.py").exists()


def test_new_default_creates_project_dir_named_after_model(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = main(["new", "fan8025"])
    assert result == 0
    assert (tmp_path / "fan8025" / "cadproject.json").exists()
    assert (tmp_path / "fan8025" / "models" / "fan8025" / "part.py").exists()


def test_new_duplicate_fails(tmp_path):
    project = tmp_path / "proj"
    main(["new", "--project", str(project), "bracket"])
    result = main(["new", "--project", str(project), "bracket"])
    assert result == 1


def test_new_duplicate_force(tmp_path):
    project = tmp_path / "proj"
    main(["new", "--project", str(project), "bracket"])
    result = main(["new", "--project", str(project), "bracket", "--force"])
    assert result == 0


def test_build_missing_model(tmp_path):
    project = tmp_path / "proj"
    main(["new", "--project", str(project), "bracket"])
    result = main(["build", "--project", str(project), "nonexistent", "--json"])
    assert result == 1


def test_validate_default_model(tmp_path):
    """Validate the default scaffold model (should build and validate ok)."""
    project = tmp_path / "proj"
    main(["new", "--project", str(project), "test_block"])
    result = main(["validate", "--project", str(project), "test_block", "--json"])
    assert result == 0


def test_version():
    import pytest
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0


def test_sync_updates_workspace(tmp_path):
    project = tmp_path / "proj"
    main(["new", "--project", str(project), "bracket"])

    # Modify a scaffold file
    claude = project / "CLAUDE.md"
    original = claude.read_text()
    claude.write_text("OLD CONTENT")

    # Sync should overwrite it
    result = main(["sync", "--project", str(project), "--json"])
    assert result == 0
    assert claude.read_text() == original

    # Model files should be untouched
    assert (project / "models" / "bracket" / "part.py").exists()


def test_sync_not_a_workspace(tmp_path):
    result = main(["sync", "--project", str(tmp_path), "--json"])
    assert result == 1


def test_sync_dry_run_does_not_overwrite(tmp_path):
    project = tmp_path / "proj"
    main(["new", "--project", str(project), "bracket"])
    claude = project / "CLAUDE.md"
    claude.write_text("LOCAL", encoding="utf-8")

    result = main(["sync", "--project", str(project), "--dry-run", "--json"])
    assert result == 0
    assert claude.read_text(encoding="utf-8") == "LOCAL"


def test_probe_cx_cy_alias(monkeypatch, tmp_path):
    project = tmp_path / "proj"
    main(["new", "--project", str(project), "bracket"])
    captured = {}

    def fake_probe(project_path, model_name, z_values=None, x_values=None, y_values=None, center=None, region=None):
        captured["center"] = center
        return {"ok": True, "stage": "probe", "model": model_name}

    monkeypatch.setattr(cli_mod, "probe_model", fake_probe)
    result = main([
        "probe", "--project", str(project), "bracket",
        "--z", "1.0", "--cx", "-10.5", "--cy", "4.25", "--json",
    ])
    assert result == 0
    assert captured["center"] == (-10.5, 4.25)


def test_probe_center_and_cx_merge(monkeypatch, tmp_path):
    project = tmp_path / "proj"
    main(["new", "--project", str(project), "bracket"])
    captured = {}

    def fake_probe(project_path, model_name, z_values=None, x_values=None, y_values=None, center=None, region=None):
        captured["center"] = center
        return {"ok": True, "stage": "probe", "model": model_name}

    monkeypatch.setattr(cli_mod, "probe_model", fake_probe)
    result = main([
        "probe", "--project", str(project), "bracket",
        "--z", "1.0", "--center=1,2", "--cx", "3", "--json",
    ])
    assert result == 0
    assert captured["center"] == (3.0, 2.0)
