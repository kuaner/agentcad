"""Tests for stale artifact detection in build_model."""
from __future__ import annotations

from pathlib import Path

import pytest

from agentcad.runner import build_model, _source_hash
from agentcad.workspace import init_workspace, new_model, model_dir


_SIMPLE_PART = """
from build123d import Box
result = Box(5, 5, 5)
"""


def _scaffold(tmp_path: Path, name: str = "widget") -> tuple[Path, Path]:
    init_workspace(tmp_path)
    new_model(tmp_path, name)
    mdir = model_dir(tmp_path, name)
    (mdir / "part.py").write_text(_SIMPLE_PART, encoding="utf-8")
    return tmp_path, mdir


def test_source_hash_changes_with_content(tmp_path):
    init_workspace(tmp_path)
    new_model(tmp_path, "mod")
    mdir = model_dir(tmp_path, "mod")
    (mdir / "part.py").write_text("result = None", encoding="utf-8")
    h1 = _source_hash(mdir)
    (mdir / "part.py").write_text("result = None  # changed", encoding="utf-8")
    h2 = _source_hash(mdir)
    assert h1 != h2


def test_source_hash_stable_without_change(tmp_path):
    init_workspace(tmp_path)
    new_model(tmp_path, "stable")
    mdir = model_dir(tmp_path, "stable")
    (mdir / "part.py").write_text("result = None", encoding="utf-8")
    assert _source_hash(mdir) == _source_hash(mdir)


def test_build_stale_skips_rebuild(tmp_path):
    project, mdir = _scaffold(tmp_path)
    r1 = build_model(project, "widget")
    assert r1["ok"] is True
    assert r1.get("skipped") is None  # first build is fresh

    r2 = build_model(project, "widget")
    assert r2["ok"] is True
    assert r2.get("skipped") is True
    assert "unchanged" in r2.get("message", "")


def test_build_force_rebuilds_even_when_cached(tmp_path):
    project, mdir = _scaffold(tmp_path)
    build_model(project, "widget")  # prime cache

    r = build_model(project, "widget", force=True)
    assert r["ok"] is True
    assert r.get("skipped") is None  # forced, so not skipped


def test_build_rebuilds_after_source_change(tmp_path):
    project, mdir = _scaffold(tmp_path)
    build_model(project, "widget")  # prime cache

    (mdir / "part.py").write_text(_SIMPLE_PART + "\n# changed", encoding="utf-8")
    r = build_model(project, "widget")
    assert r["ok"] is True
    assert r.get("skipped") is None  # source changed, rebuild required


def test_build_payload_contains_source_hash(tmp_path):
    project, mdir = _scaffold(tmp_path)
    r = build_model(project, "widget")
    assert r["ok"] is True
    assert "sourceHash" in r
    assert len(r["sourceHash"]) == 16  # truncated hex
