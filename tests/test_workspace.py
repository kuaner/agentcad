"""Tests for workspace init, project discovery, and model creation."""
from __future__ import annotations

import os
from pathlib import Path

from agentcad.workspace import (
    find_project,
    init_workspace,
    model_dir,
    new_model,
    normalize_model_name,
    outputs_dir,
    sync_workspace,
)


def test_init_workspace_creates_structure(tmp_path):
    result = init_workspace(tmp_path / "project")
    assert result["ok"] is True
    p = tmp_path / "project"
    assert (p / "cadproject.json").exists()
    assert (p / "CLAUDE.md").exists()
    assert (p / "AGENTS.md").is_symlink()
    assert os.readlink(p / "AGENTS.md") == "CLAUDE.md"
    assert (p / "references" / "build123d-guide.md").exists()
    assert (p / "references" / "validation-strategy.md").exists()
    assert (p / "models").is_dir()
    assert (p / "references" / "images").is_dir()
    assert not (p / "skills").exists()


def test_init_workspace_idempotent(tmp_path):
    init_workspace(tmp_path)
    result = init_workspace(tmp_path)
    assert result["ok"] is True
    assert "already exists" in result["message"]


def test_init_workspace_force(tmp_path):
    init_workspace(tmp_path)
    old_content = (tmp_path / "cadproject.json").read_text()
    result = init_workspace(tmp_path, force=True)
    assert result["ok"] is True
    assert "initialized" in result["message"]


def test_find_project(tmp_path):
    init_workspace(tmp_path / "myproject")
    found = find_project(tmp_path / "myproject")
    assert found.name == "myproject"


def test_find_project_from_subdir(tmp_path):
    init_workspace(tmp_path / "myproject")
    sub = tmp_path / "myproject" / "models" / "deep"
    sub.mkdir(parents=True)
    found = find_project(sub)
    assert found.name == "myproject"


def test_find_project_not_found(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        find_project(tmp_path / "nonexistent")


def test_new_model(tmp_path):
    init_workspace(tmp_path)
    result = new_model(tmp_path, "bracket")
    assert result["ok"] is True
    assert result["model"] == "bracket"
    model = tmp_path / "models" / "bracket"
    assert (model / "part.py").exists()
    assert (model / "params.json").exists()
    assert (model / "design.json").exists()
    assert (model / "outputs").is_dir()


def test_new_model_duplicate(tmp_path):
    init_workspace(tmp_path)
    new_model(tmp_path, "bracket")
    result = new_model(tmp_path, "bracket")
    assert result["ok"] is False
    assert "exists" in result["error"]["message"]


def test_new_model_force_overwrite(tmp_path):
    init_workspace(tmp_path)
    new_model(tmp_path, "bracket")
    result = new_model(tmp_path, "bracket", force=True)
    assert result["ok"] is True


def test_normalize_model_name():
    assert normalize_model_name("my bracket") == "my_bracket"
    assert normalize_model_name("foo-bar") == "foo-bar"
    assert normalize_model_name("a b c") == "a_b_c"


def test_normalize_model_name_empty():
    import pytest
    with pytest.raises(ValueError):
        normalize_model_name("   ")


def test_model_dir_and_outputs(tmp_path):
    d = model_dir(tmp_path, "test")
    assert d == tmp_path / "models" / "test"
    o = outputs_dir(tmp_path, "test")
    assert o == tmp_path / "models" / "test" / "outputs"


def test_sync_workspace_dry_run(tmp_path):
    init_workspace(tmp_path)
    claude = tmp_path / "CLAUDE.md"
    original = claude.read_text(encoding="utf-8")
    claude.write_text("LOCAL CHANGE", encoding="utf-8")

    result = sync_workspace(tmp_path, dry_run=True)
    assert result["ok"] is True
    assert result["dry_run"] is True
    assert claude.read_text(encoding="utf-8") == "LOCAL CHANGE"
    assert "CLAUDE.md" in result["planned_updates"]
    assert result["updated"] == []

    # Non-dry run should restore scaffold content.
    sync_workspace(tmp_path)
    assert claude.read_text(encoding="utf-8") == original


def test_sync_workspace_only_path(tmp_path):
    init_workspace(tmp_path)
    notes = tmp_path / "references" / "notes.md"
    claude = tmp_path / "CLAUDE.md"
    notes.write_text("ONLY THIS FILE", encoding="utf-8")
    claude.write_text("DO NOT TOUCH", encoding="utf-8")

    result = sync_workspace(tmp_path, only="references/notes.md")
    assert result["ok"] is True
    assert result["only"] == "references/notes.md"
    assert "references/notes.md" in result["updated"]
    assert "CLAUDE.md" not in result["updated"]
    assert result["agents_relinked"] is False
    assert "AGENTS.md" not in result["updated"]
    assert "DO NOT TOUCH" in claude.read_text(encoding="utf-8")


def test_sync_workspace_prune_deprecated(tmp_path):
    init_workspace(tmp_path)
    legacy = tmp_path / "skills"
    legacy.mkdir()
    (legacy / "legacy.md").write_text("old", encoding="utf-8")
    assert legacy.exists()

    dry = sync_workspace(tmp_path, dry_run=True, prune_deprecated=True)
    assert "skills" in dry["pruned"]
    assert legacy.exists()

    real = sync_workspace(tmp_path, prune_deprecated=True)
    assert "skills" in real["pruned"]
    assert not legacy.exists()
