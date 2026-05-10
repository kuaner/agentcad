"""Tests for validation pipeline: design checks and feature coverage."""
from __future__ import annotations

import json

from agentcad.validate import (
    evaluate_design_checks,
    evaluate_feature_coverage,
    stage_check,
    _attach_suggested_fixes,
    _vec_close,
)


def test_vec_close():
    assert _vec_close([1.0, 2.0, 3.0], [1.0, 2.0, 3.0], 0.0) is True
    assert _vec_close([1.0, 2.0, 3.0], [1.1, 2.0, 3.0], 0.2) is True
    assert _vec_close([1.0, 2.0, 3.0], [1.5, 2.0, 3.0], 0.2) is False
    assert _vec_close(None, [1, 2, 3], 0.0) is False


def test_stage_check_pass():
    check = stage_check("build", True, {"ok": True})
    assert check["ok"] is True
    assert check["name"] == "build"


def test_stage_check_fail():
    check = stage_check("build", False, {"error": {"message": "boom"}})
    assert check["ok"] is False
    assert check["error"]["message"] == "boom"


def test_feature_coverage_all_covered(tmp_path):
    design = {
        "features": [
            {"id": "f1", "checks": ["c1"]},
            {"id": "f2", "checks": ["c2", "c3"]},
        ],
        "checks": [
            {"id": "c1", "type": "bbox_size"},
            {"id": "c2", "type": "watertight"},
            {"id": "c3", "type": "min_triangles"},
        ],
    }
    design_path = tmp_path / "models" / "test" / "design.json"
    design_path.parent.mkdir(parents=True)
    design_path.write_text(json.dumps(design))
    import agentcad.validate as v
    original = v.model_dir
    v.model_dir = lambda p, n: p / "models" / n
    try:
        results = evaluate_feature_coverage(tmp_path, "test")
    finally:
        v.model_dir = original
    assert len(results) == 2
    assert all(r["ok"] for r in results)


def test_feature_coverage_uncovered(tmp_path):
    design = {
        "features": [
            {"id": "f1", "checks": ["c1"]},
            {"id": "f2", "checks": []},
        ],
        "checks": [{"id": "c1", "type": "bbox_size"}],
    }
    design_path = tmp_path / "models" / "test" / "design.json"
    design_path.parent.mkdir(parents=True)
    design_path.write_text(json.dumps(design))
    import agentcad.validate as v
    original = v.model_dir
    v.model_dir = lambda p, n: p / "models" / n
    try:
        results = evaluate_feature_coverage(tmp_path, "test")
    finally:
        v.model_dir = original
    assert results[0]["ok"] is True
    assert results[1]["ok"] is False


def test_design_checks_unsupported_type(tmp_path):
    design_path = tmp_path / "models" / "test" / "design.json"
    design_path.parent.mkdir(parents=True)
    design_path.write_text(json.dumps({
        "checks": [{"type": "made_up_check"}]
    }))
    import agentcad.validate as v
    original = v.model_dir
    v.model_dir = lambda p, n: p / "models" / n
    try:
        results = evaluate_design_checks(tmp_path, "test", {"geometry": {}})
    finally:
        v.model_dir = original
    assert len(results) == 1
    assert results[0]["ok"] is False
    assert "unsupported" in results[0].get("error", "")


def test_suggested_fix_with_param_ref():
    checks = [
        {"name": "hole_dia", "type": "inner_diameter_at_z", "ok": False, "actual": 4.5, "expected": 5.0},
        {"name": "wall_ok", "type": "watertight", "ok": True},
    ]
    design = {"checks": [{"id": "hole_dia", "type": "inner_diameter_at_z", "param_ref": "hole_radius"}]}
    params = {"hole_radius": 2.25}
    _attach_suggested_fixes(checks, design, params)
    assert "suggested_fix" in checks[0]
    assert checks[0]["suggested_fix"]["param"] == "hole_radius"
    assert checks[0]["suggested_fix"]["current"] == 2.25
    assert "suggested_fix" not in checks[1]


def test_suggested_fix_without_param_ref():
    checks = [
        {"name": "wall_thick", "type": "min_wall_thickness", "ok": False, "actual": 0.8, "expected": 1.0},
    ]
    _attach_suggested_fixes(checks, {}, {})
    assert "suggested_fix" in checks[0]
    assert checks[0]["suggested_fix"]["action"]
    assert "min_wall_thickness" in checks[0]["suggested_fix"]["action"]


def test_passing_check_no_suggested_fix():
    checks = [{"name": "good", "type": "watertight", "ok": True}]
    _attach_suggested_fixes(checks, {}, {})
    assert "suggested_fix" not in checks[0]
