"""Tests for the regression snapshot system."""

from __future__ import annotations

import json
from pathlib import Path

from agentcad.cli import main
from agentcad.snapshot import (
    DEFAULT_SNAPSHOT_TOLERANCES,
    SNAPSHOT_SCHEMA,
    compare_snapshot,
    load_snapshot,
    snapshot_target,
    write_snapshot,
)
from agentcad.workspace import new_model, new_variant, outputs_dir_for_variant


def _make_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "cadproject.json").write_text(
        json.dumps({"schema": "agentcad.project.v1", "units": "mm"}),
    )
    return project


class TestSnapshotTarget:
    def test_strips_volatile_fields(self, tmp_path):
        project = _make_project(tmp_path)
        target = {"kind": "model", "name": "demo", "variant": None}
        payload = {
            "ok": True,
            "validatedAt": "2026-05-12T10:00:00Z",
            "builtAt": "2026-05-12T09:59:00Z",
            "durationMs": 1234,
            "checks": [
                {"name": "bbox_size", "type": "bbox_size", "ok": True, "actual": [40, 30, 20]},
                {"name": "watertight", "type": "watertight", "ok": True},
            ],
            "artifacts": {"stl": str(project / "models" / "demo" / "outputs" / "demo.stl")},
            "message": "validation passed",
        }
        snap = snapshot_target(project, target, payload)
        assert snap["schema"] == SNAPSHOT_SCHEMA
        # Volatile fields should not appear.
        assert "validatedAt" not in snap
        assert "builtAt" not in snap
        assert "durationMs" not in snap

    def test_preserves_check_status(self, tmp_path):
        project = _make_project(tmp_path)
        target = {"kind": "model", "name": "demo", "variant": None}
        payload = {
            "ok": False,
            "checks": [
                {"name": "bbox_size", "type": "bbox_size", "ok": True, "actual": [40, 30, 20]},
                {"name": "watertight", "type": "watertight", "ok": False},
            ],
        }
        snap = snapshot_target(project, target, payload)
        checks = snap["checks"]
        assert checks["bbox_size"]["ok"] is True
        assert checks["watertight"]["ok"] is False
        assert checks["bbox_size"]["actual"] == [40, 30, 20]

    def test_preserves_target_info(self, tmp_path):
        project = _make_project(tmp_path)
        target = {"kind": "assembly", "name": "fan_with_screen", "variant": None}
        payload = {"ok": True, "checks": []}
        snap = snapshot_target(project, target, payload)
        assert snap["target"]["kind"] == "assembly"
        assert snap["target"]["name"] == "fan_with_screen"
        assert snap["target"]["variant"] is None

    def test_artifact_presence_from_payload(self, tmp_path):
        project = _make_project(tmp_path)
        target = {"kind": "model", "name": "demo", "variant": None}
        # Create a fake artifact.
        stl_path = project / "models" / "demo" / "outputs" / "demo.stl"
        stl_path.parent.mkdir(parents=True)
        stl_path.write_text("fake stl")
        payload = {
            "ok": True,
            "artifacts": {"stl": str(stl_path)},
            "checks": [],
        }
        snap = snapshot_target(project, target, payload)
        assert snap["artifacts"]["stl"] is True

    def test_extracts_model_geometry_from_geometry_json(self, tmp_path):
        project = _make_project(tmp_path)
        target = {"kind": "model", "name": "demo", "variant": None}
        geometry_path = project / "models" / "demo" / "outputs" / "geometry.json"
        geometry_path.parent.mkdir(parents=True)
        geometry_path.write_text(json.dumps({
            "ok": True,
            "stage": "measure",
            "geometry": {
                "bbox": {"size": [40.0, 30.0, 20.0]},
                "mesh": {"triangles": 12, "watertight": True},
                "mass_properties": {"volume": 24000.0},
            },
        }))

        snap = snapshot_target(project, target, {"ok": True, "checks": []})

        assert snap["geometry"]["bbox_size"] == [40.0, 30.0, 20.0]
        assert snap["geometry"]["triangles"] == 12
        assert snap["geometry"]["volume"] == 24000.0

    def test_extracts_assembly_geometry_summary(self, tmp_path):
        project = _make_project(tmp_path)
        target = {"kind": "assembly", "name": "fan_with_screen", "variant": None}
        payload = {
            "ok": True,
            "checks": [],
            "geometry_summary": {
                "triangle_count": 48,
                "bbox": {"size": [80.0, 80.0, 26.0]},
            },
        }

        snap = snapshot_target(project, target, payload)

        assert snap["geometry"]["bbox_size"] == [80.0, 80.0, 26.0]
        assert snap["geometry"]["triangles"] == 48


class TestWriteLoadSnapshot:
    def test_write_creates_file(self, tmp_path):
        project = _make_project(tmp_path)
        target = {"kind": "model", "name": "demo", "variant": None}
        payload = {"ok": True, "checks": []}
        path = write_snapshot(project, target, payload)
        assert path.exists()

    def test_load_returns_snapshot(self, tmp_path):
        project = _make_project(tmp_path)
        target = {"kind": "model", "name": "demo", "variant": None}
        payload = {"ok": True, "checks": [{"name": "bbox_size", "type": "bbox_size", "ok": True}]}
        write_snapshot(project, target, payload)
        loaded = load_snapshot(project, target)
        assert loaded is not None
        assert loaded["schema"] == SNAPSHOT_SCHEMA
        assert loaded["checks"]["bbox_size"]["ok"] is True

    def test_load_missing_returns_none(self, tmp_path):
        project = _make_project(tmp_path)
        target = {"kind": "model", "name": "nonexistent", "variant": None}
        assert load_snapshot(project, target) is None

    def test_variant_filename(self, tmp_path):
        project = _make_project(tmp_path)
        target = {"kind": "model", "name": "bracket", "variant": "large"}
        payload = {"ok": True, "checks": []}
        path = write_snapshot(project, target, payload)
        assert "bracket__variant_large.json" in path.name

    def test_assembly_filename(self, tmp_path):
        project = _make_project(tmp_path)
        target = {"kind": "assembly", "name": "fan_with_screen", "variant": None}
        payload = {"ok": True, "checks": []}
        path = write_snapshot(project, target, payload)
        assert "assemblies" in str(path)
        assert "fan_with_screen.json" in path.name


class TestSnapshotCLI:
    def test_write_specific_variant_target(self, tmp_path):
        project = _make_project(tmp_path)
        new_model(project, "bracket")
        new_variant(project, "bracket", "large")
        out_dir = outputs_dir_for_variant(project, "bracket", "large")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "validation.json").write_text(json.dumps({
            "ok": True,
            "stage": "validate",
            "checks": [{"name": "bbox_size", "type": "bbox_size", "ok": True}],
            "artifacts": {"validation": str(out_dir / "validation.json")},
        }))

        result = main(["--project", str(project), "snapshot", "write", "--target", "bracket:large"])

        assert result == 0
        assert (project / ".agentcad" / "snapshots" / "models" / "bracket__variant_large.json").exists()


class TestCompareSnapshot:
    def test_unchanged_returns_ok(self):
        baseline = {
            "schema": SNAPSHOT_SCHEMA,
            "target": {"kind": "model", "name": "demo", "variant": None},
            "checks": {"bbox_size": {"type": "bbox_size", "ok": True}},
            "geometry": {"bbox_size": [40, 30, 20], "volume": 24000, "triangles": 12},
            "artifacts": {"stl": True},
        }
        current = baseline.copy()
        result = compare_snapshot(current, baseline)
        assert result["ok"] is True
        assert result["changes"]["checks_regressed"] == []
        assert result["changes"]["geometry_drift"] == {}
        assert result["changes"]["artifact_changes"] == []

    def test_check_regression(self):
        baseline = {
            "schema": SNAPSHOT_SCHEMA,
            "target": {},
            "checks": {"bbox_size": {"type": "bbox_size", "ok": True}},
            "geometry": {},
            "artifacts": {},
        }
        current = {
            "schema": SNAPSHOT_SCHEMA,
            "target": {},
            "checks": {"bbox_size": {"type": "bbox_size", "ok": False}},
            "geometry": {},
            "artifacts": {},
        }
        result = compare_snapshot(current, baseline)
        assert result["ok"] is False
        assert "bbox_size" in result["changes"]["checks_regressed"]

    def test_check_fixed(self):
        baseline = {
            "schema": SNAPSHOT_SCHEMA,
            "target": {},
            "checks": {"watertight": {"type": "watertight", "ok": False}},
            "geometry": {},
            "artifacts": {},
        }
        current = {
            "schema": SNAPSHOT_SCHEMA,
            "target": {},
            "checks": {"watertight": {"type": "watertight", "ok": True}},
            "geometry": {},
            "artifacts": {},
        }
        result = compare_snapshot(current, baseline)
        assert "watertight" in result["changes"]["checks_fixed"]

    def test_check_added(self):
        baseline = {
            "schema": SNAPSHOT_SCHEMA,
            "target": {},
            "checks": {},
            "geometry": {},
            "artifacts": {},
        }
        current = {
            "schema": SNAPSHOT_SCHEMA,
            "target": {},
            "checks": {"new_check": {"type": "min_wall_thickness", "ok": True}},
            "geometry": {},
            "artifacts": {},
        }
        result = compare_snapshot(current, baseline)
        assert "new_check" in result["changes"]["checks_added"]

    def test_check_removed(self):
        baseline = {
            "schema": SNAPSHOT_SCHEMA,
            "target": {},
            "checks": {"old_check": {"type": "bbox_size", "ok": True}},
            "geometry": {},
            "artifacts": {},
        }
        current = {
            "schema": SNAPSHOT_SCHEMA,
            "target": {},
            "checks": {},
            "geometry": {},
            "artifacts": {},
        }
        result = compare_snapshot(current, baseline)
        assert "old_check" in result["changes"]["checks_removed"]

    def test_bbox_drift_exceeds_tolerance(self):
        baseline = {
            "schema": SNAPSHOT_SCHEMA,
            "target": {},
            "checks": {},
            "geometry": {"bbox_size": [40.0, 30.0, 20.0]},
            "artifacts": {},
        }
        current = {
            "schema": SNAPSHOT_SCHEMA,
            "target": {},
            "checks": {},
            "geometry": {"bbox_size": [40.1, 30.0, 20.0]},
            "artifacts": {},
        }
        result = compare_snapshot(current, baseline)
        assert "bbox_size_delta" in result["changes"]["geometry_drift"]

    def test_bbox_drift_within_tolerance(self):
        baseline = {
            "schema": SNAPSHOT_SCHEMA,
            "target": {},
            "checks": {},
            "geometry": {"bbox_size": [40.0, 30.0, 20.0]},
            "artifacts": {},
        }
        current = {
            "schema": SNAPSHOT_SCHEMA,
            "target": {},
            "checks": {},
            "geometry": {"bbox_size": [40.02, 30.0, 20.0]},
            "artifacts": {},
        }
        result = compare_snapshot(current, baseline)
        assert "bbox_size_delta" not in result["changes"]["geometry_drift"]

    def test_volume_drift_exceeds_relative_tolerance(self):
        baseline = {
            "schema": SNAPSHOT_SCHEMA,
            "target": {},
            "checks": {},
            "geometry": {"volume": 24000},
            "artifacts": {},
        }
        current = {
            "schema": SNAPSHOT_SCHEMA,
            "target": {},
            "checks": {},
            "geometry": {"volume": 24050},
            "artifacts": {},
        }
        result = compare_snapshot(current, baseline, tolerances={"volume_rel": 0.001})
        assert "volume_delta" in result["changes"]["geometry_drift"]

    def test_volume_drift_within_relative_tolerance(self):
        baseline = {
            "schema": SNAPSHOT_SCHEMA,
            "target": {},
            "checks": {},
            "geometry": {"volume": 24000},
            "artifacts": {},
        }
        current = {
            "schema": SNAPSHOT_SCHEMA,
            "target": {},
            "checks": {},
            "geometry": {"volume": 24100},
            "artifacts": {},
        }
        result = compare_snapshot(current, baseline)
        assert "volume_delta" not in result["changes"]["geometry_drift"]

    def test_triangle_count_drift(self):
        baseline = {
            "schema": SNAPSHOT_SCHEMA,
            "target": {},
            "checks": {},
            "geometry": {"triangles": 12},
            "artifacts": {},
        }
        current = {
            "schema": SNAPSHOT_SCHEMA,
            "target": {},
            "checks": {},
            "geometry": {"triangles": 36},
            "artifacts": {},
        }
        result = compare_snapshot(current, baseline)
        assert "triangles_delta" in result["changes"]["geometry_drift"]

    def test_bbox_length_mismatch_is_drift(self):
        baseline = {
            "schema": SNAPSHOT_SCHEMA,
            "target": {},
            "checks": {},
            "geometry": {"bbox_size": [40.0, 30.0, 20.0]},
            "artifacts": {},
        }
        current = {
            "schema": SNAPSHOT_SCHEMA,
            "target": {},
            "checks": {},
            "geometry": {"bbox_size": [40.0, 30.0]},
            "artifacts": {},
        }
        result = compare_snapshot(current, baseline)
        assert "bbox_size_delta" in result["changes"]["geometry_drift"]

    def test_artifact_added(self):
        baseline = {
            "schema": SNAPSHOT_SCHEMA,
            "target": {},
            "checks": {},
            "geometry": {},
            "artifacts": {},
        }
        current = {
            "schema": SNAPSHOT_SCHEMA,
            "target": {},
            "checks": {},
            "geometry": {},
            "artifacts": {"stl": True},
        }
        result = compare_snapshot(current, baseline)
        assert any("added" in c for c in result["changes"]["artifact_changes"])

    def test_artifact_removed(self):
        baseline = {
            "schema": SNAPSHOT_SCHEMA,
            "target": {},
            "checks": {},
            "geometry": {},
            "artifacts": {"stl": True},
        }
        current = {
            "schema": SNAPSHOT_SCHEMA,
            "target": {},
            "checks": {},
            "geometry": {},
            "artifacts": {},
        }
        result = compare_snapshot(current, baseline)
        assert any("removed" in c for c in result["changes"]["artifact_changes"])

    def test_artifact_status_changed(self):
        baseline = {
            "schema": SNAPSHOT_SCHEMA,
            "target": {},
            "checks": {},
            "geometry": {},
            "artifacts": {"stl": True},
        }
        current = {
            "schema": SNAPSHOT_SCHEMA,
            "target": {},
            "checks": {},
            "geometry": {},
            "artifacts": {"stl": False},
        }
        result = compare_snapshot(current, baseline)
        assert any("changed" in c for c in result["changes"]["artifact_changes"])

    def test_custom_tolerances(self):
        baseline = {
            "schema": SNAPSHOT_SCHEMA,
            "target": {},
            "checks": {},
            "geometry": {"bbox_size": [40.0, 30.0, 20.0]},
            "artifacts": {},
        }
        current = {
            "schema": SNAPSHOT_SCHEMA,
            "target": {},
            "checks": {},
            "geometry": {"bbox_size": [40.01, 30.0, 20.0]},
            "artifacts": {},
        }
        # With a tighter tolerance, this small drift should be flagged.
        result = compare_snapshot(current, baseline, tolerances={"bbox_abs_mm": 0.005})
        assert "bbox_size_delta" in result["changes"]["geometry_drift"]
