"""Tests for P3.3 improved suggested_fix payloads: likely_source, next_commands, param_candidates."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentcad.validate import (
    _attach_suggested_fixes,
    _likely_source,
    _next_commands,
    _find_param_candidates,
)
from agentcad.workspace import init_workspace, new_model, model_dir


@pytest.fixture()
def project(tmp_path):
    init_workspace(tmp_path)
    new_model(tmp_path, "thing")
    return tmp_path


def _write_design(mdir: Path, design: dict) -> None:
    (mdir / "design.json").write_text(json.dumps(design), encoding="utf-8")


def _write_params(mdir: Path, params: dict) -> None:
    (mdir / "params.json").write_text(json.dumps(params), encoding="utf-8")


class TestLikelySource:
    def test_bbox_with_actual_is_geometry(self):
        assert _likely_source({"type": "bbox_size", "actual": [10, 10, 10]}) == "geometry"

    def test_bbox_without_actual_is_contract(self):
        assert _likely_source({"type": "bbox_size"}) == "contract"

    def test_inner_diameter_is_geometry(self):
        assert _likely_source({"type": "inner_diameter_at_z"}) == "geometry"

    def test_min_clearance_is_contract(self):
        assert _likely_source({"type": "min_clearance"}) == "contract"

    def test_hole_accessibility_is_geometry(self):
        assert _likely_source({"type": "hole_accessibility"}) == "geometry"

    def test_artifact_exists_is_artifact(self):
        assert _likely_source({"type": "artifact_exists"}) == "artifact"

    def test_unknown_type_is_unknown(self):
        assert _likely_source({"type": "custom_check"}) == "unknown"


class TestNextCommands:
    def test_bbox_failure_suggests_measure_and_render(self):
        cmds = _next_commands({"type": "bbox_size"}, "thing")
        assert f"agentcad measure thing" in cmds
        assert f"agentcad render thing --views iso,front,top" in cmds

    def test_inner_diameter_suggests_probe_and_render(self):
        cmds = _next_commands({"type": "inner_diameter_at_z", "z": 5, "center": [0, 0]}, "thing")
        assert any("agentcad probe thing" in c for c in cmds)
        assert any("--section-z" in c for c in cmds)

    def test_hole_accessibility_suggests_section_render(self):
        cmds = _next_commands({"type": "hole_accessibility"}, "thing")
        assert any("--section-z" in c for c in cmds)

    def test_min_clearance_suggests_precheck(self):
        cmds = _next_commands({"type": "min_clearance"}, "thing")
        assert "agentcad precheck thing" in cmds

    def test_artifact_exists_suggests_build(self):
        cmds = _next_commands({"type": "artifact_exists"}, "thing")
        assert "agentcad build thing" in cmds

    def test_feature_coverage_suggests_suggest_checks(self):
        cmds = _next_commands({"type": "feature_coverage"}, "thing")
        assert "agentcad suggest-checks thing" in cmds

    def test_min_wall_thickness_suggests_probe_scan(self):
        cmds = _next_commands({"type": "min_wall_thickness"}, "thing")
        assert any("agentcad probe thing --scan" in c for c in cmds)


class TestParamCandidates:
    def test_bbox_finds_width_height_params(self):
        check = {"type": "bbox_size"}
        params = {"plate_width": 40, "plate_height": 20, "hole_diameter": 5}
        candidates = _find_param_candidates(check, params)
        assert "plate_width" in candidates
        assert "plate_height" in candidates
        assert "hole_diameter" not in candidates

    def test_inner_diameter_finds_diameter_params(self):
        check = {"type": "inner_diameter_at_z"}
        params = {"hole_diameter": 5, "plate_width": 40}
        candidates = _find_param_candidates(check, params)
        assert "hole_diameter" in candidates

    def test_hole_accessibility_finds_fastener_params(self):
        check = {"type": "hole_accessibility"}
        params = {"fastener_diameter": 8, "wall_thickness": 2}
        candidates = _find_param_candidates(check, params)
        assert "fastener_diameter" in candidates

    def test_no_keywords_returns_empty(self):
        check = {"type": "watertight"}
        params = {"plate_width": 40}
        assert _find_param_candidates(check, params) == []

    def test_limits_to_three_candidates(self):
        check = {"type": "bbox_size"}
        params = {"w": 1, "width": 2, "width_extra": 3, "depth_size": 4, "height_dim": 5}
        candidates = _find_param_candidates(check, params)
        assert len(candidates) <= 3


class TestAttachSuggestedFixesEnrichment:
    def test_generic_fix_gets_likely_source_and_next_commands(self):
        checks = [{"name": "bbox1", "type": "bbox_size", "ok": False, "actual": [10, 10, 10], "expected": [40, 30, 20]}]
        design = {"checks": [{"id": "bbox1", "type": "bbox_size"}]}
        params = {}
        _attach_suggested_fixes(checks, design, params, name="thing")
        fix = checks[0]["suggested_fix"]
        assert "likely_source" in fix
        assert "next_commands" in fix
        assert fix["likely_source"] == "geometry"

    def test_param_fix_gets_likely_source_and_next_commands(self):
        checks = [{"name": "bbox1", "type": "bbox_size", "ok": False, "actual": [10, 10, 10], "expected": [40, 30, 20]}]
        design = {"checks": [{"id": "bbox1", "type": "bbox_size", "param_ref": "plate_width"}]}
        params = {"plate_width": 40}
        _attach_suggested_fixes(checks, design, params, name="thing")
        fix = checks[0]["suggested_fix"]
        assert "likely_source" in fix
        assert "next_commands" in fix
        assert fix["param"] == "plate_width"

    def test_generic_fix_with_param_candidates(self):
        checks = [{"name": "bbox1", "type": "bbox_size", "ok": False, "actual": [10, 10, 10], "expected": [40, 30, 20]}]
        design = {"checks": [{"id": "bbox1", "type": "bbox_size"}]}
        params = {"plate_width": 40, "plate_height": 20}
        _attach_suggested_fixes(checks, design, params, name="thing")
        fix = checks[0]["suggested_fix"]
        assert "param_candidates" in fix
        assert "plate_width" in fix["param_candidates"]
        assert "plate_height" in fix["param_candidates"]

    def test_param_fix_no_param_candidates_when_param_ref_exists(self):
        # When param_ref exists and matches, param_candidates should NOT appear
        # because the fix already has the specific param.
        checks = [{"name": "bbox1", "type": "bbox_size", "ok": False, "actual": [10, 10, 10], "expected": [40, 30, 20]}]
        design = {"checks": [{"id": "bbox1", "type": "bbox_size", "param_ref": "plate_width"}]}
        params = {"plate_width": 40, "plate_height": 20}
        _attach_suggested_fixes(checks, design, params, name="thing")
        fix = checks[0]["suggested_fix"]
        assert "param" in fix
        assert "param_candidates" not in fix

    def test_passing_check_gets_no_suggested_fix(self):
        checks = [{"name": "bbox1", "type": "bbox_size", "ok": True}]
        design = {"checks": [{"id": "bbox1", "type": "bbox_size"}]}
        params = {}
        _attach_suggested_fixes(checks, design, params, name="thing")
        assert "suggested_fix" not in checks[0]