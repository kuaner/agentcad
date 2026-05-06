"""Tests for CLI dispatch and auto-init behavior."""
from __future__ import annotations

import json
from pathlib import Path

from agentcad.cli import main


def test_new_auto_init(tmp_path):
    result = main(["new", "--project", str(tmp_path / "newproject"), "bracket"])
    assert result == 0
    assert (tmp_path / "newproject" / "cadproject.json").exists()
    assert (tmp_path / "newproject" / "CLAUDE.md").exists()
    assert (tmp_path / "newproject" / "models" / "bracket" / "part.py").exists()


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
