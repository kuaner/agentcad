"""Tests for P1.5 weak-check review gates: feature classification,
category-specific warnings, and blocking review gates.

Review gates promote high-confidence warnings (holes without accessibility,
features without geometry checks) to blocking checklist items that gate
delivery.
"""
from __future__ import annotations

from pathlib import Path

from agentcad.contract import (
    classify_feature,
    evaluate_feature_evidence_matrix_dict,
    evaluate_weak_check_warnings_dict,
)
from agentcad.review import review_model
from agentcad.workspace import init_workspace, new_model, model_dir

import json
import pytest


def _write_design(mdir: Path, design: dict) -> None:
    (mdir / "design.json").write_text(json.dumps(design), encoding="utf-8")


@pytest.fixture()
def project(tmp_path):
    init_workspace(tmp_path)
    new_model(tmp_path, "thing")
    return tmp_path


# ── classify_feature ────────────────────────────────────────────────────────


class TestClassifyFeature:
    def test_hole_by_id(self):
        tags = classify_feature({"id": "mounting_holes"})
        assert "hole" in tags

    def test_hole_by_intent(self):
        tags = classify_feature({"id": "m4", "intent": "M4 bolt holes"})
        assert "hole" in tags

    def test_hole_by_counterbore(self):
        tags = classify_feature({"id": "cb", "intent": "counterbore for M3"})
        assert "hole" in tags

    def test_attachment_by_id(self):
        tags = classify_feature({"id": "reinforcement_rib"})
        assert "load_bearing_attachment" in tags

    def test_attachment_by_intent(self):
        tags = classify_feature({"id": "s", "intent": "support flange"})
        assert "load_bearing_attachment" in tags

    def test_interface_by_id(self):
        tags = classify_feature({"id": "dovetail_socket"})
        assert "interface" in tags

    def test_unclassified(self):
        tags = classify_feature({"id": "plain_wall", "intent": "outer envelope"})
        assert tags == set()

    def test_multi_category(self):
        tags = classify_feature({"id": "bolt_hole_dovetail", "intent": "bolt hole dovetail mate"})
        assert "hole" in tags
        assert "interface" in tags


# ── weak-check warnings with severity ────────────────────────────────────────


class TestWeakCheckSeverity:
    def test_no_checks_is_blocking(self, project):
        mdir = model_dir(project, "thing")
        _write_design(mdir, {
            "features": [{"id": "orphan"}],
            "checks": [],
        })
        warnings = evaluate_weak_check_warnings_dict(
            json.loads((mdir / "design.json").read_text())
        )
        assert len(warnings) == 1
        assert warnings[0]["severity"] == "blocking"
        assert warnings[0]["missing"] == "any_check"

    def test_no_geometry_checks_is_blocking(self, project):
        mdir = model_dir(project, "thing")
        _write_design(mdir, {
            "features": [{"id": "shell", "checks": ["bbox", "wt"]}],
            "checks": [
                {"id": "bbox", "type": "bbox_size", "expected": [10, 10, 10], "tolerance": 0.1},
                {"id": "wt", "type": "watertight"},
            ],
        })
        warnings = evaluate_weak_check_warnings_dict(
            json.loads((mdir / "design.json").read_text())
        )
        assert len(warnings) == 1
        assert warnings[0]["severity"] == "blocking"
        assert warnings[0]["missing"] == "geometry_check"

    def test_hole_without_accessibility_is_blocking(self, project):
        mdir = model_dir(project, "thing")
        _write_design(mdir, {
            "features": [{"id": "m4_holes", "intent": "M4 mounting holes", "checks": ["diameter"]}],
            "checks": [
                {"id": "diameter", "type": "inner_diameter_at_z", "z": 5.0, "expected": 4.0, "center": [0, 0]},
            ],
        })
        warnings = evaluate_weak_check_warnings_dict(
            json.loads((mdir / "design.json").read_text())
        )
        blocking = [w for w in warnings if w["severity"] == "blocking"]
        assert len(blocking) == 1
        assert blocking[0]["missing"] == "hole_accessibility"
        assert "hole" in blocking[0]["category"]

    def test_hole_with_accessibility_has_no_blocking(self, project):
        mdir = model_dir(project, "thing")
        _write_design(mdir, {
            "features": [{"id": "m4_holes", "intent": "M4 holes", "checks": ["diameter", "access"]}],
            "checks": [
                {"id": "diameter", "type": "inner_diameter_at_z", "z": 5.0, "expected": 4.0, "center": [0, 0]},
                {"id": "access", "type": "hole_accessibility", "z": 5.0, "center": [0, 0], "hole_diameter": 4.0, "clearance_diameter": 8.0},
            ],
        })
        warnings = evaluate_weak_check_warnings_dict(
            json.loads((mdir / "design.json").read_text())
        )
        blocking = [w for w in warnings if w["severity"] == "blocking"]
        assert blocking == []

    def test_rib_without_root_check_is_warning(self, project):
        mdir = model_dir(project, "thing")
        _write_design(mdir, {
            "features": [{"id": "reinforcement_rib", "intent": "rib for strength", "checks": ["bbox"]}],
            "checks": [
                {"id": "bbox", "type": "bbox_size", "expected": [10, 10, 10], "tolerance": 0.1},
            ],
        })
        warnings = evaluate_weak_check_warnings_dict(
            json.loads((mdir / "design.json").read_text())
        )
        # bbox_size is not a geometry check, so first warning is blocking (no geometry check).
        # If we add a geometry check but no root check, it's a warning.
        _write_design(mdir, {
            "features": [{"id": "reinforcement_rib", "intent": "rib for strength", "checks": ["diameter"]}],
            "checks": [
                {"id": "diameter", "type": "inner_diameter_at_z", "z": 5.0, "expected": 4.0, "center": [0, 0]},
            ],
        })
        warnings = evaluate_weak_check_warnings_dict(
            json.loads((mdir / "design.json").read_text())
        )
        non_blocking = [w for w in warnings if w["severity"] != "blocking"]
        root_warnings = [w for w in non_blocking if w["missing"] == "root_interface_check"]
        assert len(root_warnings) == 1
        assert "load_bearing_attachment" in root_warnings[0]["category"]

    def test_rib_with_root_check_has_no_warning(self, project):
        mdir = model_dir(project, "thing")
        _write_design(mdir, {
            "features": [{"id": "reinforcement_rib", "intent": "rib for strength", "checks": ["wall"]}],
            "checks": [
                {"id": "wall", "type": "min_wall_thickness", "z": 1.0, "region": [[0, 0], [10, 10]], "min_mm": 1.0},
            ],
        })
        warnings = evaluate_weak_check_warnings_dict(
            json.loads((mdir / "design.json").read_text())
        )
        root_warnings = [w for w in warnings if w["missing"] == "root_interface_check"]
        assert root_warnings == []

    def test_non_hole_cylinder_is_not_blocked(self, project):
        """A cylinder that is not named as a hole should not get hole-specific blocking."""
        mdir = model_dir(project, "thing")
        _write_design(mdir, {
            "features": [{"id": "pillar", "intent": "support pillar", "checks": ["diameter"]}],
            "checks": [
                {"id": "diameter", "type": "inner_diameter_at_z", "z": 5.0, "expected": 6.0, "center": [0, 0]},
            ],
        })
        warnings = evaluate_weak_check_warnings_dict(
            json.loads((mdir / "design.json").read_text())
        )
        hole_warnings = [w for w in warnings if "hole" in w.get("category", [])]
        assert hole_warnings == []


class TestFeatureEvidenceMatrix:
    def test_hole_requires_access_and_interface_risk_evidence(self):
        matrix = evaluate_feature_evidence_matrix_dict({
            "features": [{"id": "m4_hole", "intent": "M4 mounting hole", "checks": ["diameter"]}],
            "checks": [
                {"id": "diameter", "type": "inner_diameter_at_z", "z": 3.0, "expected": 4.0, "center": [0, 0]},
            ],
        })

        row = matrix[0]
        assert row["evidence"]["position"]["ok"] is True
        assert row["evidence"]["dimensions"]["ok"] is True
        assert row["evidence"]["access"]["ok"] is False
        assert row["evidence"]["interface_risk"]["ok"] is False
        assert row["missing"] == ["access", "interface_risk"]

    def test_review_exposes_feature_evidence_matrix_gate(self, project):
        mdir = model_dir(project, "thing")
        _write_design(mdir, {
            "features": [{"id": "m4_hole", "intent": "M4 hole", "checks": ["diameter", "access"]}],
            "checks": [
                {"id": "diameter", "type": "inner_diameter_at_z", "z": 5.0, "expected": 4.0, "center": [0, 0]},
                {
                    "id": "access",
                    "type": "hole_accessibility",
                    "axis": "z",
                    "z": 5.0,
                    "center": [0, 0],
                    "hole_diameter": 4.0,
                    "clearance_diameter": 8.0,
                },
            ],
        })

        result = review_model(project, "thing")
        gate = next(item for item in result["checklist"] if item["id"] == "feature_evidence_matrix")
        assert gate["ok"] is False
        assert result["feature_evidence_matrix"][0]["missing"] == ["interface_risk"]


# ── review blocking gates ────────────────────────────────────────────────────


class TestReviewBlockingGates:
    def test_blocking_warning_creates_review_gate(self, project):
        """Blocking weak-check warnings become checklist items that fail."""
        mdir = model_dir(project, "thing")
        _write_design(mdir, {
            "features": [{"id": "m4_holes", "intent": "M4 holes", "checks": ["diameter"]}],
            "checks": [
                {"id": "diameter", "type": "inner_diameter_at_z", "z": 5.0, "expected": 4.0, "center": [0, 0]},
            ],
        })
        result = review_model(project, "thing")
        blocking_items = [c for c in result["checklist"] if c["id"] == "blocking_weak_checks_resolved"]
        assert len(blocking_items) == 1
        assert blocking_items[0]["ok"] is False

    def test_no_blocking_warnings_means_gate_passes(self, project):
        mdir = model_dir(project, "thing")
        _write_design(mdir, {
            "features": [{"id": "duct", "checks": ["diameter"]}],
            "checks": [
                {"id": "diameter", "type": "inner_diameter_at_z", "z": 5.0, "expected": 20.0, "tolerance": 1.0},
            ],
        })
        result = review_model(project, "thing")
        blocking_items = [c for c in result["checklist"] if c["id"] == "blocking_weak_checks_resolved"]
        assert len(blocking_items) == 1
        assert blocking_items[0]["ok"] is True

    def test_deferred_followups_skip_blocking(self, project):
        """Blocking warnings are not duplicated in deferred followups."""
        mdir = model_dir(project, "thing")
        _write_design(mdir, {
            "features": [{"id": "orphan"}],
            "checks": [],
        })
        result = review_model(project, "thing")
        followups = result.get("deferred_followups") or []
        blocking_followups = [f for f in followups if f.get("severity") == "blocking"]
        assert blocking_followups == []

    def test_non_blocking_warnings_are_deferred(self, project):
        mdir = model_dir(project, "thing")
        _write_design(mdir, {
            "features": [{"id": "reinforcement_rib", "intent": "rib", "checks": ["wall"]}],
            "checks": [
                {"id": "wall", "type": "min_wall_thickness", "z": 1.0, "region": [[0, 0], [10, 10]], "min_mm": 1.0},
            ],
        })
        result = review_model(project, "thing")
        blocking_items = [c for c in result["checklist"] if c["id"] == "blocking_weak_checks_resolved"]
        assert blocking_items[0]["ok"] is True


# ── backward compatibility ──────────────────────────────────────────────────


class TestBackwardCompatibility:
    def test_old_tests_still_see_feature_field(self, project):
        """Existing test_weak_check.py checks still work with new warning shape."""
        mdir = model_dir(project, "thing")
        _write_design(mdir, {
            "features": [{"id": "orphan"}],
            "checks": [],
        })
        warnings = evaluate_weak_check_warnings_dict(
            json.loads((mdir / "design.json").read_text())
        )
        assert len(warnings) == 1
        assert warnings[0]["feature"] == "orphan"

    def test_hint_field_present(self, project):
        mdir = model_dir(project, "thing")
        _write_design(mdir, {
            "features": [{"id": "orphan"}],
            "checks": [],
        })
        warnings = evaluate_weak_check_warnings_dict(
            json.loads((mdir / "design.json").read_text())
        )
        assert "hint" in warnings[0]

    def test_category_field_is_new(self, project):
        mdir = model_dir(project, "thing")
        _write_design(mdir, {
            "features": [{"id": "m4_holes", "intent": "M4 holes", "checks": ["diameter"]}],
            "checks": [
                {"id": "diameter", "type": "inner_diameter_at_z", "z": 5.0, "expected": 4.0, "center": [0, 0]},
            ],
        })
        warnings = evaluate_weak_check_warnings_dict(
            json.loads((mdir / "design.json").read_text())
        )
        blocking = [w for w in warnings if w["severity"] == "blocking"]
        assert "category" in blocking[0]
