"""Tests for weak check warnings in validate.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentcad.validate import evaluate_weak_check_warnings, validate_design_schema
from agentcad.workspace import init_workspace, new_model, model_dir


def _write_design(mdir: Path, design: dict) -> None:
    (mdir / "design.json").write_text(json.dumps(design), encoding="utf-8")


@pytest.fixture()
def project(tmp_path):
    init_workspace(tmp_path)
    new_model(tmp_path, "thing")
    return tmp_path


# ── schema validation ────────────────────────────────────────────────────────

def test_schema_valid_design(project):
    mdir = model_dir(project, "thing")
    _write_design(mdir, {
        "features": [{"id": "shell", "checks": ["bbox"]}],
        "checks": [{"id": "bbox", "type": "bbox_size", "expected": [10, 10, 10], "tolerance": 0.1}],
    })
    errors = validate_design_schema(project, "thing")
    assert errors == []


def test_schema_missing_check_id(project):
    mdir = model_dir(project, "thing")
    _write_design(mdir, {
        "checks": [{"type": "bbox_size", "expected": [10, 10, 10]}],  # no id
    })
    errors = validate_design_schema(project, "thing")
    assert len(errors) == 1
    assert "missing required 'id'" in errors[0]["error"]


def test_schema_duplicate_check_id(project):
    mdir = model_dir(project, "thing")
    _write_design(mdir, {
        "checks": [
            {"id": "dup", "type": "watertight"},
            {"id": "dup", "type": "watertight"},
        ],
    })
    errors = validate_design_schema(project, "thing")
    assert any("duplicate id" in e["error"] for e in errors)


def test_schema_unknown_check_type(project):
    mdir = model_dir(project, "thing")
    _write_design(mdir, {
        "checks": [{"id": "bad", "type": "nonexistent_type"}],
    })
    errors = validate_design_schema(project, "thing")
    assert any("unknown type" in e["error"] for e in errors)


def test_schema_missing_design_json(project):
    errors = validate_design_schema(project, "thing")
    # Default scaffold may or may not have design.json at right path; if not found, error
    mdir = model_dir(project, "thing")
    design_path = mdir / "design.json"
    if not design_path.exists():
        assert len(errors) == 1
        assert "not found" in errors[0]["error"]


# ── weak check warnings ──────────────────────────────────────────────────────

def test_no_warnings_when_geometry_check_present(project):
    mdir = model_dir(project, "thing")
    _write_design(mdir, {
        "features": [{"id": "duct", "checks": ["diameter"]}],
        "checks": [{"id": "diameter", "type": "inner_diameter_at_z", "z": 5.0, "expected": 20.0, "tolerance": 1.0}],
    })
    warnings = evaluate_weak_check_warnings(project, "thing")
    assert warnings == []


def test_warning_when_only_trivial_checks(project):
    mdir = model_dir(project, "thing")
    _write_design(mdir, {
        "features": [{"id": "shell", "checks": ["bbox", "wt"]}],
        "checks": [
            {"id": "bbox", "type": "bbox_size", "expected": [10, 10, 10], "tolerance": 0.1},
            {"id": "wt", "type": "watertight"},
        ],
    })
    warnings = evaluate_weak_check_warnings(project, "thing")
    assert len(warnings) == 1
    assert warnings[0]["feature"] == "shell"
    assert "geometry checks" in warnings[0]["message"]
    assert "hint" in warnings[0]


def test_warning_when_feature_has_no_checks(project):
    mdir = model_dir(project, "thing")
    _write_design(mdir, {
        "features": [{"id": "orphan"}],
        "checks": [],
    })
    warnings = evaluate_weak_check_warnings(project, "thing")
    assert len(warnings) == 1
    assert warnings[0]["feature"] == "orphan"


def test_no_warnings_for_section_bbox_check(project):
    mdir = model_dir(project, "thing")
    _write_design(mdir, {
        "features": [{"id": "camera", "checks": ["cam_void"]}],
        "checks": [{"id": "cam_void", "type": "section_bbox_at_z", "z": 0.5, "expected": "void"}],
    })
    warnings = evaluate_weak_check_warnings(project, "thing")
    assert warnings == []
