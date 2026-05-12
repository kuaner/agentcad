"""Negative regression fixtures for known common-error patterns.

Each fixture tests that a deliberately broken contract fails for the intended
check type, verifying that the validation system catches the specific failure
class it was designed for.
"""

from __future__ import annotations

import json
from pathlib import Path

from agentcad.checks import CheckContext
from agentcad.checks.relations import evaluate_hole_accessibility, evaluate_min_wall_thickness
from agentcad.contract import validate_design_schema_issues


def _write_design(mdir: Path, design: dict) -> None:
    mdir.mkdir(parents=True, exist_ok=True)
    (mdir / "design.json").write_text(json.dumps(design))


class TestHoleWallInterference:
    """A hole edge that is too close to a wall (or buried under one).

    Cylinder at (0,0) radius 2.25 extends to x=2.25. Wall box starts at x=3.
    Edge-to-edge clearance = 3 - 2.25 = 0.75mm, which is less than min_mm=1.0.
    """

    def test_min_clearance_catches_hole_wall_interference(self, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        (project / "cadproject.json").write_text(json.dumps({"schema": "agentcad.project.v1"}))
        mdir = project / "models" / "hole_wall" / "design.json"
        design = {
            "schema": "design-spec.v1",
            "features": [
                {"id": "base_holes", "intent": "M4 mounting holes", "checks": ["hole_wall_clear"]},
            ],
            "checks": [
                {
                    "id": "hole_wall_clear",
                    "type": "min_clearance",
                    "feature_a": {"type": "cylinder", "axis": "z", "center": [0, 0], "radius": 2.25, "z_range": [0, 10]},
                    "feature_b": {"type": "box", "x_range": [3, 9], "y_range": [-10, 10], "z_range": [0, 10]},
                    "min_mm": 1.0,
                },
            ],
        }
        _write_design(mdir.parent, design)

        # Run precheck — min_clearance should fail because edge-to-edge
        # clearance is only 0.75mm (hole edge at 2.25, wall left edge at 3).
        from agentcad.precheck import precheck_model
        import agentcad.workspace as ws
        original = ws.model_dir
        ws.model_dir = lambda p, n: p / "models" / n
        try:
            result = precheck_model(project, "hole_wall")
        finally:
            ws.model_dir = original

        # Find the min_clearance check.
        clearance_checks = [c for c in result.get("checks", []) if c.get("type") == "min_clearance"]
        assert len(clearance_checks) == 1
        assert clearance_checks[0]["ok"] is False


class TestHoleToEdgeBreak:
    """A hole too close to a part edge, risking structural break.

    Hole cylinder at (4,0) radius 3.3 → outer edge at x=7.3.
    Part box right edge at x=5. Clearance = 5 - 7.3 = -2.3 (interference).
    min_clearance with min_mm=2.0 should catch this.
    """

    def test_min_clearance_catches_hole_near_edge(self, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        (project / "cadproject.json").write_text(json.dumps({"schema": "agentcad.project.v1"}))
        mdir = project / "models" / "hole_edge" / "design.json"
        design = {
            "schema": "design-spec.v1",
            "features": [
                {"id": "mounting_hole", "intent": "hole near part edge", "checks": ["edge_clear"]},
            ],
            "checks": [
                {
                    "id": "edge_clear",
                    "type": "min_clearance",
                    "feature_a": {"type": "cylinder", "axis": "z", "center": [4, 0], "radius": 3.3, "z_range": [0, 10]},
                    "feature_b": {"type": "box", "x_range": [-5, 5], "y_range": [-5, 5], "z_range": [0, 10]},
                    "min_mm": 2.0,
                },
            ],
        }
        _write_design(mdir.parent, design)

        from agentcad.precheck import precheck_model
        import agentcad.workspace as ws
        original = ws.model_dir
        ws.model_dir = lambda p, n: p / "models" / n
        try:
            result = precheck_model(project, "hole_edge")
        finally:
            ws.model_dir = original

        clearance_checks = [c for c in result.get("checks", []) if c.get("type") == "min_clearance"]
        assert len(clearance_checks) == 1
        # Hole edge at 4+3.3=7.3, part right edge at 5.
        # Interference — clearance is negative, check should fail.
        assert clearance_checks[0]["ok"] is False


class TestShallowThroughHole:
    """A through-hole check at mid-Z passes, but the hole is shallow.

    inner_diameter_at_z at Z=depth/2 only proves the hole exists at that Z.
    This pattern is a known false-pass. The correct fix is to check near Z=0
    and Z=top as well, which should fail on a shallow hole.
    """

    def test_schema_warns_about_missing_z_range_verification(self):
        """Schema should not prevent this, but it's a known weakness."""
        design = {
            "checks": [
                {"id": "hole_mid_z", "type": "inner_diameter_at_z", "z": 5.0, "expected": 4.0, "center": [0, 0]},
            ],
        }
        issues = validate_design_schema_issues(design)
        # The schema currently doesn't warn about single-Z hole checks,
        # but the hard rules in the template CLAUDE.md document this pitfall.
        # This test documents that the system accepts the check even though
        # it's a known weakness.
        assert not any(i.path.startswith("checks[0]") for i in issues)


class TestBlockedToolAccess:
    """A hole that a tool cannot reach because something blocks the approach.

    hole_accessibility should catch this.
    """

    def test_hole_accessibility_fails_when_blocked(self, monkeypatch, tmp_path):
        """When tool envelope has blocking material, hole_accessibility fails."""
        from agentcad.geometry import hole_accessibility_at_z

        def fake_accessibility(triangles, z, center, hole_radius, clearance_radius):
            return {"ok": False, "blocking_point_count": 5, "min_blocking_radius": 2.0}

        monkeypatch.setattr("agentcad.checks.relations.hole_accessibility_at_z", fake_accessibility)

        ctx = CheckContext(
            project=tmp_path, name="m", measure={}, get_triangles=lambda: [], out_dir=tmp_path,
        )
        check = {
            "id": "blocked_access",
            "type": "hole_accessibility",
            "z": 2.0,
            "center": [0.0, 0.0],
            "hole_diameter": 4.5,
            "clearance_diameter": 12.0,
        }
        result = evaluate_hole_accessibility(check, ctx)
        assert result["ok"] is False
        assert result["blocking_point_count"] == 5


class TestDetachedFeature:
    """A lip, rib, or tab that appears connected in iso view but is actually
    detached or only touching at an edge.

    This class of failure passes bbox + watertight but is structurally wrong.
    It should be caught by section_bbox_at_z or min_wall_thickness at the
    root/interface of the feature.
    """

    def test_min_wall_thickness_catches_thin_attachment(self, monkeypatch, tmp_path):
        """A rib with near-zero wall thickness at its base should fail."""
        def fake_thickness(triangles, z, region=None, sample_resolution=0.5):
            return {"ok": True, "min_thickness_mm": 0.1, "min_pair": None, "point_count": 100}

        monkeypatch.setattr("agentcad.checks.relations.min_wall_thickness_at_z", fake_thickness)

        ctx = CheckContext(
            project=tmp_path, name="m", measure={}, get_triangles=lambda: [], out_dir=tmp_path,
        )
        check = {
            "id": "rib_root_thickness",
            "type": "min_wall_thickness",
            "z": 1.0,
            "region": [[0, 0], [10, 10]],
            "min_mm": 1.0,
        }
        result = evaluate_min_wall_thickness(check, ctx)
        assert result["ok"] is False
        assert result["actual_mm"] < 1.0


class TestVoidWithoutRegion:
    """A section_bbox_at_z void check without region can falsely pass
    on an empty slice.
    """

    def test_schema_warns_void_without_region(self):
        design = {
            "checks": [
                {"id": "void_no_region", "type": "section_bbox_at_z", "z": 5.0, "expected": "void"},
            ],
        }
        issues = validate_design_schema_issues(design)
        assert any(i.path == "checks[0].region" for i in issues)
        assert any(i.severity == "warning" for i in issues)

    def test_void_with_region_passes_schema(self):
        design = {
            "checks": [
                {"id": "void_with_region", "type": "section_bbox_at_z", "z": 5.0, "expected": "void",
                 "region": [[0, 0], [10, 10]]},
            ],
        }
        issues = validate_design_schema_issues(design)
        assert not any(i.path.startswith("checks[0]") for i in issues)


class TestControlModels:
    """Passing control fixtures for each failure class, proving that
    a correctly-designed model validates.
    """

    def test_min_clearance_passes_when_sufficient(self, tmp_path):
        """Cylinder at (0,0) r=2.25 + box left edge at x=10 = 7.75mm clearance ≥ 1.0mm."""
        project = tmp_path / "project"
        project.mkdir()
        (project / "cadproject.json").write_text(json.dumps({"schema": "agentcad.project.v1"}))
        mdir = project / "models" / "good_clearance" / "design.json"
        design = {
            "schema": "design-spec.v1",
            "features": [
                {"id": "holes", "intent": "holes with adequate clearance", "checks": ["clear_ok"]},
            ],
            "checks": [
                {
                    "id": "clear_ok",
                    "type": "min_clearance",
                    "feature_a": {"type": "cylinder", "axis": "z", "center": [0, 0], "radius": 2.25, "z_range": [0, 10]},
                    "feature_b": {"type": "box", "x_range": [10, 16], "y_range": [-10, 10], "z_range": [0, 10]},
                    "min_mm": 1.0,
                },
            ],
        }
        _write_design(mdir.parent, design)

        from agentcad.precheck import precheck_model
        import agentcad.workspace as ws
        original = ws.model_dir
        ws.model_dir = lambda p, n: p / "models" / n
        try:
            result = precheck_model(project, "good_clearance")
        finally:
            ws.model_dir = original

        clearance_checks = [c for c in result.get("checks", []) if c.get("type") == "min_clearance"]
        assert len(clearance_checks) == 1
        assert clearance_checks[0]["ok"] is True

    def test_hole_accessibility_passes_when_clear(self, monkeypatch, tmp_path):
        """When tool envelope has no blocking material, hole_accessibility passes."""
        def fake_accessibility(triangles, z, center, hole_radius, clearance_radius):
            return {"ok": True, "blocking_point_count": 0, "min_blocking_radius": None}

        monkeypatch.setattr("agentcad.checks.relations.hole_accessibility_at_z", fake_accessibility)

        ctx = CheckContext(
            project=tmp_path, name="m", measure={}, get_triangles=lambda: [], out_dir=tmp_path,
        )
        check = {
            "id": "clear_access",
            "type": "hole_accessibility",
            "z": 2.0,
            "center": [0.0, 0.0],
            "hole_diameter": 4.5,
            "clearance_diameter": 12.0,
        }
        result = evaluate_hole_accessibility(check, ctx)
        assert result["ok"] is True

    def test_min_wall_thickness_passes_when_thick_enough(self, monkeypatch, tmp_path):
        def fake_thickness(triangles, z, region=None, sample_resolution=0.5):
            return {"ok": True, "min_thickness_mm": 3.0, "min_pair": None, "point_count": 100}

        monkeypatch.setattr("agentcad.checks.relations.min_wall_thickness_at_z", fake_thickness)

        ctx = CheckContext(
            project=tmp_path, name="m", measure={}, get_triangles=lambda: [], out_dir=tmp_path,
        )
        check = {
            "id": "rib_root_ok",
            "type": "min_wall_thickness",
            "z": 1.0,
            "region": [[0, 0], [10, 10]],
            "min_mm": 1.0,
        }
        result = evaluate_min_wall_thickness(check, ctx)
        assert result["ok"] is True