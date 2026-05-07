"""Tests for the build123d runner: execution, export, error handling."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentcad.runner import build_model
from agentcad.workspace import init_workspace, new_model


def _write_part(model_dir: Path, source: str) -> None:
    (model_dir / "part.py").write_text(source, encoding="utf-8")


def _scaffold(tmp_path: Path, name: str = "widget") -> tuple[Path, Path]:
    init_workspace(tmp_path)
    new_model(tmp_path, name)
    return tmp_path, tmp_path / "models" / name


@pytest.fixture()
def project(tmp_path):
    return tmp_path


def test_build_missing_source(project):
    init_workspace(project)
    new_model(project, "empty")
    model_root = project / "models" / "empty"
    (model_root / "part.py").unlink()
    result = build_model(project, "empty")
    assert result["ok"] is False
    assert result["stage"] == "build"
    assert result["error"]["type"] == "SourceMissing"


def test_build_syntax_error(project):
    p, model_root = _scaffold(project, "bad")
    _write_part(model_root, "result = (  # broken syntax\n")
    result = build_model(project, "bad")
    assert result["ok"] is False
    assert result["stage"] == "build"
    assert "SyntaxError" in result["error"]["type"]


def test_build_missing_result(project):
    p, model_root = _scaffold(project, "noresult")
    _write_part(model_root, "x = 1  # no result variable\n")
    result = build_model(project, "noresult")
    assert result["ok"] is False
    assert result["error"]["type"] == "MissingResult"


def test_build_runtime_error(project):
    p, model_root = _scaffold(project, "boom")
    _write_part(model_root, "raise ValueError('intentional error')\nresult = None\n")
    result = build_model(project, "boom")
    assert result["ok"] is False
    assert result["error"]["type"] == "ValueError"
    assert "intentional error" in result["error"]["message"]


def test_build_error_includes_line_number(project):
    p, model_root = _scaffold(project, "lineno")
    _write_part(model_root, "x = 1\ny = 2\nraise RuntimeError('fail here')\nresult = None\n")
    result = build_model(project, "lineno")
    assert result["ok"] is False
    assert result["error"].get("line") == 3


def test_build_success_produces_artifacts(project):
    p, model_root = _scaffold(project, "cube")
    _write_part(
        model_root,
        "from build123d import *\n"
        "with BuildPart() as bp:\n"
        "    Box(10, 10, 10)\n"
        "result = bp.part\n",
    )
    result = build_model(project, "cube")
    assert result["ok"] is True
    assert result["stage"] == "build"
    assert Path(result["artifacts"]["step"]).exists()
    assert Path(result["artifacts"]["stl"]).exists()


def test_build_metadata_written(project):
    p, model_root = _scaffold(project, "meta")
    _write_part(
        model_root,
        "from build123d import *\n"
        "with BuildPart() as bp:\n"
        "    Box(5, 5, 5)\n"
        "result = bp.part\n"
        "metadata = {'schema': 'test', 'value': 42}\n",
    )
    result = build_model(project, "meta")
    assert result["ok"] is True
    meta_path = Path(result["artifacts"]["metadata"])
    assert meta_path.exists()
    data = json.loads(meta_path.read_text())
    assert data["value"] == 42


def test_build_metadata_non_serializable_fails(project):
    p, model_root = _scaffold(project, "badmeta")
    _write_part(
        model_root,
        "from build123d import *\n"
        "with BuildPart() as bp:\n"
        "    Box(5, 5, 5)\n"
        "result = bp.part\n"
        "metadata = {'bad': object()}\n",
    )
    result = build_model(project, "badmeta")
    assert result["ok"] is False
    assert result["stage"] == "metadata"


def test_build_idempotent(project):
    p, model_root = _scaffold(project, "repeat")
    _write_part(
        model_root,
        "from build123d import *\n"
        "with BuildPart() as bp:\n"
        "    Box(8, 8, 8)\n"
        "result = bp.part\n",
    )
    r1 = build_model(project, "repeat")
    r2 = build_model(project, "repeat")
    assert r1["ok"] is True
    assert r2["ok"] is True
