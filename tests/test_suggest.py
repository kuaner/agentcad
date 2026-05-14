"""Tests for P3.2 suggest-checks command: missing check suggestions."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentcad.suggest import evaluate_suggestion_quality, suggest_checks, suggest_from_contract
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


class TestSuggestChecksBasic:
    def test_no_design_returns_error(self, project):
        mdir = model_dir(project, "thing")
        design_path = mdir / "design.json"
        if design_path.exists():
            design_path.unlink()
        result = suggest_checks(project, "thing")
        assert result["ok"] is False
        assert result["design_found"] is False
        assert result["suggestions"] == []

    def test_empty_features_no_suggestions(self, project):
        mdir = model_dir(project, "thing")
        _write_design(mdir, {"features": [], "checks": []})
        result = suggest_checks(project, "thing")
        assert result["ok"] is True
        assert result["suggestions"] == []

    def test_feature_with_no_checks_gets_any_check_suggestion(self, project):
        mdir = model_dir(project, "thing")
        _write_design(mdir, {
            "features": [{"id": "shell", "checks": []}],
            "checks": [],
        })
        result = suggest_checks(project, "thing")
        assert result["suggestion_quality"]["template_count"] == len(result["suggestions"])
        s = next(s for s in result["suggestions"] if s["missing"] == "any_check")
        assert s["feature"] == "shell"
        assert s["missing"] == "any_check"
        assert {"dimension_check", "position_check"} <= {s["missing"] for s in result["suggestions"]}

    def test_feature_with_only_bbox_gets_geometry_suggestion(self, project):
        mdir = model_dir(project, "thing")
        _write_design(mdir, {
            "features": [{"id": "shell", "checks": ["shell_bbox"]}],
            "checks": [{"id": "shell_bbox", "type": "bbox_size", "expected": [10, 10, 10], "tolerance": 0.1}],
        })
        result = suggest_checks(project, "thing")
        s = next(s for s in result["suggestions"] if s["missing"] == "geometry_check")
        assert s["missing"] == "geometry_check"
        assert "type" in s["template"]


class TestSuggestHoleChecks:
    def test_hole_with_diameter_but_no_access(self, project):
        mdir = model_dir(project, "thing")
        _write_design(mdir, {
            "features": [{"id": "mounting_holes", "checks": ["hole_dia"]}],
            "checks": [{"id": "hole_dia", "type": "inner_diameter_at_z", "z": 5, "expected": 4.0, "tolerance": 0.1}],
        })
        result = suggest_checks(project, "thing")
        suggestions = result["suggestions"]
        assert any(s["missing"] == "hole_accessibility" for s in suggestions)
        hole_s = next(s for s in suggestions if s["missing"] == "hole_accessibility")
        assert hole_s["template"]["type"] == "hole_accessibility"

    def test_hole_with_access_already_present_no_suggestion(self, project):
        mdir = model_dir(project, "thing")
        _write_design(mdir, {
            "features": [{"id": "mounting_holes", "checks": ["hole_dia", "hole_access"]}],
            "checks": [
                {"id": "hole_dia", "type": "inner_diameter_at_z", "z": 5, "expected": 4.0, "tolerance": 0.1},
                {"id": "hole_access", "type": "hole_accessibility", "axis": "z"},
            ],
        })
        result = suggest_checks(project, "thing")
        assert not any(s["missing"] == "hole_accessibility" for s in result["suggestions"])

    def test_hole_feature_infers_diameter_from_params(self, project):
        mdir = model_dir(project, "thing")
        _write_design(mdir, {
            "features": [{"id": "mounting_holes", "checks": ["hole_dia"]}],
            "checks": [{"id": "hole_dia", "type": "inner_diameter_at_z", "z": 5, "expected": 4.0, "tolerance": 0.1}],
        })
        _write_params(mdir, {"hole_diameter": 4.0, "hole_clearance": 8.0})
        result = suggest_checks(project, "thing")
        hole_s = next(s for s in result["suggestions"] if s["missing"] == "hole_accessibility")
        assert hole_s["template"]["hole_diameter"] == "4.0"
        assert hole_s["template"]["clearance_diameter"] == "8.0"

    def test_non_hole_cylinder_is_not_suggested_as_hole(self, project):
        """Non-hole cylinders (e.g., 'bearing_seat') should not get hole_accessibility suggestion
        unless classified as a hole."""
        mdir = model_dir(project, "thing")
        _write_design(mdir, {
            "features": [{"id": "bearing_seat", "checks": ["seat_dia"]}],
            "checks": [{"id": "seat_dia", "type": "inner_diameter_at_z", "z": 5, "expected": 10.0, "tolerance": 0.1}],
        })
        result = suggest_checks(project, "thing")
        # "bearing_seat" does not match HOLE_WORDS (no hole, bore, screw, etc.)
        assert not any(s["missing"] == "hole_accessibility" for s in result["suggestions"])


class TestSuggestAttachmentChecks:
    def test_rib_with_no_root_check(self, project):
        mdir = model_dir(project, "thing")
        _write_design(mdir, {
            "features": [{"id": "support_rib", "checks": ["rib_bbox"]}],
            "checks": [{"id": "rib_bbox", "type": "bbox_size", "expected": [5, 3, 10], "tolerance": 0.1}],
        })
        result = suggest_checks(project, "thing")
        suggestions = result["suggestions"]
        # rib_bbox is only bbox, no geometry check → should get geometry_check suggestion
        # AND rib is load_bearing → should get root_interface_check if geometry checks exist
        # But bbox_size is not in GEOMETRY_CHECK_TYPES, so first suggestion is geometry_check
        assert any(s["missing"] == "geometry_check" for s in suggestions)

    def test_rib_with_section_but_no_wall_thickness(self, project):
        mdir = model_dir(project, "thing")
        _write_design(mdir, {
            "features": [{"id": "support_rib", "checks": ["rib_section"]}],
            "checks": [{"id": "rib_section", "type": "section_bbox_at_z", "z": 5, "expected": [5, 3], "tolerance": 0.1}],
        })
        result = suggest_checks(project, "thing")
        assert any(s["missing"] == "root_interface_check" for s in result["suggestions"])
        root_s = next(s for s in result["suggestions"] if s["missing"] == "root_interface_check")
        assert root_s["template"]["type"] in ("min_wall_thickness", "min_clearance")

    def test_rib_with_wall_thickness_no_suggestion(self, project):
        mdir = model_dir(project, "thing")
        _write_design(mdir, {
            "features": [{"id": "support_rib", "checks": ["rib_section", "rib_wall"]}],
            "checks": [
                {"id": "rib_section", "type": "section_bbox_at_z", "z": 5, "expected": [5, 3], "tolerance": 0.1},
                {"id": "rib_wall", "type": "min_wall_thickness", "axis": "z", "min_mm": 1.5},
            ],
        })
        result = suggest_checks(project, "thing")
        assert not any(s["missing"] == "root_interface_check" for s in result["suggestions"])


class TestSuggestTemplateQuality:
    def test_hole_no_checks_gets_accessibility_template(self, project):
        mdir = model_dir(project, "thing")
        _write_design(mdir, {
            "features": [{"id": "mounting_hole", "checks": []}],
            "checks": [],
        })
        result = suggest_checks(project, "thing")
        s = result["suggestions"][0]
        assert s["template"]["type"] == "hole_accessibility"

    def test_interface_no_checks_gets_clearance_template(self, project):
        mdir = model_dir(project, "thing")
        _write_design(mdir, {
            "features": [{"id": "snap_socket", "checks": []}],
            "checks": [],
        })
        result = suggest_checks(project, "thing")
        s = result["suggestions"][0]
        assert s["template"]["type"] == "min_clearance"

    def test_unclassified_no_checks_gets_bbox_template(self, project):
        mdir = model_dir(project, "thing")
        _write_design(mdir, {
            "features": [{"id": "body", "checks": []}],
            "checks": [],
        })
        result = suggest_checks(project, "thing")
        s = result["suggestions"][0]
        assert s["template"]["type"] == "bbox_size"

    def test_wall_thickness_infers_from_params(self, project):
        mdir = model_dir(project, "thing")
        _write_design(mdir, {
            "features": [{"id": "support_rib", "checks": ["rib_section"]}],
            "checks": [{"id": "rib_section", "type": "section_bbox_at_z", "z": 5, "expected": [5, 3], "tolerance": 0.1}],
        })
        _write_params(mdir, {"wall_thickness": 2.0})
        result = suggest_checks(project, "thing")
        root_s = next(s for s in result["suggestions"] if s["missing"] == "root_interface_check")
        assert root_s["template"]["min_mm"] == "2.0"

    def test_suggest_includes_evidence_matrix_and_probe_plan(self, project):
        mdir = model_dir(project, "thing")
        _write_design(mdir, {
            "features": [{"id": "mounting_hole", "checks": ["hole_dia"]}],
            "checks": [
                {
                    "id": "hole_dia",
                    "type": "inner_diameter_at_z",
                    "z": 5,
                    "expected": 4.0,
                    "center": [10, -2],
                    "tolerance": 0.2,
                }
            ],
        })

        result = suggest_checks(project, "thing")

        assert result["feature_evidence_matrix"][0]["feature"] == "mounting_hole"
        assert "interface_risk" in result["feature_evidence_matrix"][0]["missing"]
        commands = [p["command"] for p in result["probe_plan"]]
        assert "agentcad probe thing --z 5 --cx 10 --cy -2" in commands

    def test_hole_access_template_uses_metadata_axis(self, project):
        mdir = model_dir(project, "thing")
        _write_design(mdir, {
            "features": [{"id": "m3_hole", "checks": ["dia"]}],
            "checks": [{"id": "dia", "type": "inner_diameter_at_z", "expected": 3.4}],
        })
        _write_params(mdir, {"hole_diameter": 3.4})
        (mdir / "metadata.json").write_text(json.dumps({
            "schema": "agentcad.part.metadata.v1",
            "interfaces": {
                "m3_hole_screw_axis": {
                    "kind": "screw_axis",
                    "axis": {"point": [3.0, 4.0, 12.0], "direction": [0.0, 0.0, -1.0]},
                    "clearance_diameter": 7.0,
                }
            },
        }), encoding="utf-8")

        result = suggest_checks(project, "thing")
        access = next(s for s in result["suggestions"] if s["missing"] == "hole_accessibility")
        template = access["template"]
        assert template["axis"] == "z"
        assert template["z"] == 12.0
        assert template["center"] == [3.0, 4.0]
        assert template["clearance_diameter"] == "7.0"

    def test_suggest_from_contract_in_memory_entry(self):
        result = suggest_from_contract(
            "fixture",
            {
                "features": [{"id": "body", "checks": []}],
                "checks": [],
            },
            params={"length": 10.0, "depth": 8.0, "height": 4.0, "tolerance": 0.2},
            geometry={
                "geometry": {
                    "bbox": {
                        "min": [-5.0, -4.0, 0.0],
                        "max": [5.0, 4.0, 4.0],
                        "center": [0.0, 0.0, 2.0],
                        "size": [10.0, 8.0, 4.0],
                    }
                }
            },
        )

        assert result["ok"] is True
        assert result["model"] == "fixture"
        assert result["design_found"] is True
        assert "suggestion_quality" in result

    def test_feature_can_emit_multiple_evidence_suggestions(self):
        result = suggest_from_contract(
            "fixture",
            {
                "features": [
                    {
                        "id": "support_rib",
                        "description": "Load bearing support rib at a thin root.",
                        "checks": [],
                    }
                ],
                "checks": [],
            },
            params={"length": 20.0, "depth": 10.0, "height": 8.0, "wall_thickness": 2.0},
            geometry={
                "geometry": {
                    "bbox": {
                        "min": [-10.0, -5.0, 0.0],
                        "max": [10.0, 5.0, 8.0],
                        "center": [0.0, 0.0, 4.0],
                        "size": [20.0, 10.0, 8.0],
                    }
                }
            },
        )

        types = {s["template"]["type"] for s in result["suggestions"]}
        missings = {s["missing"] for s in result["suggestions"]}
        assert {"min_wall_thickness", "section_bbox_at_z", "feature_position"} <= types
        assert {"wall_thickness_check", "dimension_check", "position_check"} <= missings

    def test_suggestion_quality_counts_placeholders(self):
        quality = evaluate_suggestion_quality([
            {
                "feature": "f",
                "missing": "dimension_check",
                "template": {
                    "id": "f_bbox",
                    "type": "bbox_size",
                    "expected": ["<width>", "<depth>", 5.0],
                },
            },
            {
                "feature": "g",
                "missing": "position_check",
                "template": {
                    "id": "g_position",
                    "type": "feature_position",
                    "point": [0.0, 0.0, 1.0],
                    "expected": "solid",
                },
            },
        ])

        assert quality["template_count"] == 2
        assert quality["placeholder_count"] == 2
        assert quality["concrete_template_count"] == 1
        assert quality["placeholders"][0]["path"] == "template.expected[0]"

    def test_params_metadata_and_geometry_eliminate_placeholders(self):
        result = suggest_from_contract(
            "fixture",
            {
                "features": [{"id": "m3_hole", "checks": []}],
                "checks": [],
                "failure_modes": [
                    {
                        "id": "edge",
                        "mode": "edge_breakout",
                        "severity": "high",
                        "affects": ["m3_hole"],
                        "required_evidence": ["position", "dimensions", "access", "interface_risk"],
                    }
                ],
            },
            params={
                "length": 24.0,
                "depth": 18.0,
                "height": 6.0,
                "hole_diameter": 3.4,
                "tool_diameter": 7.0,
                "edge_clearance": 2.0,
            },
            metadata={
                "interfaces": {
                    "m3_hole_axis": {
                        "axis": {"point": [8.0, 0.0, 3.0], "direction": [0.0, 0.0, 1.0]},
                        "clearance_diameter": 7.0,
                        "inner_cylinder": {
                            "type": "cylinder",
                            "axis": "z",
                            "center": [8.0, 0.0],
                            "radius": 1.7,
                            "z_range": [0.0, 6.0],
                        },
                    }
                }
            },
            geometry={
                "geometry": {
                    "bbox": {
                        "min": [-12.0, -9.0, 0.0],
                        "max": [12.0, 9.0, 6.0],
                        "center": [0.0, 0.0, 3.0],
                        "size": [24.0, 18.0, 6.0],
                    }
                }
            },
        )

        assert result["suggestion_quality"]["placeholder_count"] == 0
