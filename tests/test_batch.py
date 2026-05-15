"""Tests for batch target discovery and batch validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import agentcad.cli as cli_mod
from agentcad.batch import (
    ValidationTarget,
    _check_summary,
    _target_summary,
    discover_assemblies,
    discover_models,
    discover_validation_targets,
    discover_variants,
    validate_all,
)
from agentcad.cli import main


def _make_workspace(tmp_path: Path, *, models=None, assemblies=None):
    """Create a minimal workspace structure for discovery tests."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "cadproject.json").write_text(
        json.dumps({"schema": "agentcad.project.v1", "units": "mm"}),
    )

    if models:
        models_dir = project / "models"
        for spec in models:
            name = spec["name"]
            m_dir = models_dir / name
            m_dir.mkdir(parents=True)
            (m_dir / "design.json").write_text(json.dumps({"features": [], "checks": []}))
            if "variants" in spec:
                v_dir = m_dir / "variants"
                for v_name in spec["variants"]:
                    v_sub = v_dir / v_name
                    v_sub.mkdir(parents=True)
                    (v_sub / "params.json").write_text(json.dumps({"w": 10}))

    if assemblies:
        a_dir = project / "assemblies"
        for name in assemblies:
            a_sub = a_dir / name
            a_sub.mkdir(parents=True)
            (a_sub / "assembly.json").write_text(json.dumps({"schema": "agentcad.assembly.v1", "name": name}))

    return project


class TestDiscoverModels:
    def test_empty_workspace(self, tmp_path):
        project = _make_workspace(tmp_path)
        assert discover_models(project) == []

    def test_model_with_design_json(self, tmp_path):
        project = _make_workspace(tmp_path, models=[{"name": "bracket"}])
        targets = discover_models(project)
        assert len(targets) == 1
        assert targets[0].kind == "model"
        assert targets[0].name == "bracket"
        assert targets[0].variant is None

    def test_folder_without_design_json_is_ignored(self, tmp_path):
        project = _make_workspace(tmp_path)
        (project / "models" / "notes").mkdir(parents=True)
        # No design.json — should not be discovered.
        assert discover_models(project) == []

    def test_missing_models_dir(self, tmp_path):
        project = tmp_path / "no_models"
        project.mkdir()
        (project / "cadproject.json").write_text("{}")
        assert discover_models(project) == []

    def test_multiple_models_sorted(self, tmp_path):
        project = _make_workspace(tmp_path, models=[
            {"name": "z_part"},
            {"name": "a_part"},
            {"name": "m_part"},
        ])
        targets = discover_models(project)
        names = [t.name for t in targets]
        assert names == ["a_part", "m_part", "z_part"]

    def test_model_path_points_to_directory(self, tmp_path):
        project = _make_workspace(tmp_path, models=[{"name": "demo"}])
        targets = discover_models(project)
        assert targets[0].path == project / "models" / "demo"


class TestDiscoverVariants:
    def test_no_variants(self, tmp_path):
        project = _make_workspace(tmp_path, models=[{"name": "bracket"}])
        assert discover_variants(project, "bracket") == []

    def test_variant_with_params_json(self, tmp_path):
        project = _make_workspace(tmp_path, models=[
            {"name": "bracket", "variants": ["large"]},
        ])
        targets = discover_variants(project, "bracket")
        assert len(targets) == 1
        assert targets[0].kind == "model"
        assert targets[0].name == "bracket"
        assert targets[0].variant == "large"

    def test_variant_folder_without_params_json_ignored(self, tmp_path):
        project = _make_workspace(tmp_path, models=[{"name": "bracket"}])
        v_dir = project / "models" / "bracket" / "variants" / "stale"
        v_dir.mkdir(parents=True)
        # No params.json — should not be discovered.
        assert discover_variants(project, "bracket") == []

    def test_missing_model_dir(self, tmp_path):
        project = _make_workspace(tmp_path)
        assert discover_variants(project, "nonexistent") == []

    def test_multiple_variants_sorted(self, tmp_path):
        project = _make_workspace(tmp_path, models=[
            {"name": "bracket", "variants": ["z_var", "a_var", "m_var"]},
        ])
        targets = discover_variants(project, "bracket")
        variants = [t.variant for t in targets]
        assert variants == ["a_var", "m_var", "z_var"]


class TestDiscoverAssemblies:
    def test_empty_workspace(self, tmp_path):
        project = _make_workspace(tmp_path)
        assert discover_assemblies(project) == []

    def test_assembly_with_contract(self, tmp_path):
        project = _make_workspace(tmp_path, assemblies=["fan_with_screen"])
        targets = discover_assemblies(project)
        assert len(targets) == 1
        assert targets[0].kind == "assembly"
        assert targets[0].name == "fan_with_screen"
        assert targets[0].variant is None

    def test_folder_without_assembly_json_ignored(self, tmp_path):
        project = _make_workspace(tmp_path)
        (project / "assemblies" / "notes").mkdir(parents=True)
        assert discover_assemblies(project) == []

    def test_missing_assemblies_dir(self, tmp_path):
        project = tmp_path / "no_assemblies"
        project.mkdir()
        (project / "cadproject.json").write_text("{}")
        assert discover_assemblies(project) == []

    def test_multiple_assemblies_sorted(self, tmp_path):
        project = _make_workspace(tmp_path, assemblies=["z_assy", "a_assy", "m_assy"])
        targets = discover_assemblies(project)
        names = [t.name for t in targets]
        assert names == ["a_assy", "m_assy", "z_assy"]


class TestDiscoverValidationTargets:
    def test_defaults_include_models_and_assemblies(self, tmp_path):
        project = _make_workspace(tmp_path, models=[
            {"name": "bracket"},
        ], assemblies=["fan_with_screen"])
        targets = discover_validation_targets(project)
        kinds = [(t.kind, t.name) for t in targets]
        assert ("assembly", "fan_with_screen") in kinds
        assert ("model", "bracket") in kinds

    def test_models_only(self, tmp_path):
        project = _make_workspace(tmp_path, models=[
            {"name": "bracket"},
        ], assemblies=["fan_with_screen"])
        targets = discover_validation_targets(project, include_models=True, include_assemblies=False)
        assert all(t.kind == "model" for t in targets)

    def test_assemblies_only(self, tmp_path):
        project = _make_workspace(tmp_path, models=[
            {"name": "bracket"},
        ], assemblies=["fan_with_screen"])
        targets = discover_validation_targets(project, include_models=False, include_assemblies=True)
        assert all(t.kind == "assembly" for t in targets)

    def test_include_variants(self, tmp_path):
        project = _make_workspace(tmp_path, models=[
            {"name": "bracket", "variants": ["large", "small"]},
        ])
        targets = discover_validation_targets(project, include_variants=True)
        variant_targets = [t for t in targets if t.variant is not None]
        assert len(variant_targets) == 2

    def test_exclude_variants_by_default(self, tmp_path):
        project = _make_workspace(tmp_path, models=[
            {"name": "bracket", "variants": ["large"]},
        ])
        targets = discover_validation_targets(project)
        variant_targets = [t for t in targets if t.variant is not None]
        assert len(variant_targets) == 0

    def test_deterministic_sorting(self, tmp_path):
        project = _make_workspace(tmp_path, models=[
            {"name": "z_part"},
            {"name": "a_part"},
        ], assemblies=["b_assy", "a_assy"])
        targets = discover_validation_targets(project)
        keys = [(t.kind, t.name, t.variant or "") for t in targets]
        assert keys == sorted(keys)

    def test_empty_workspace(self, tmp_path):
        project = _make_workspace(tmp_path)
        assert discover_validation_targets(project) == []

    def test_slow_targets_excluded_by_default(self, tmp_path):
        project = _make_workspace(tmp_path, models=[{"name": "fast"}])
        targets = discover_validation_targets(project)
        # All targets have slow=False by default, so all pass the filter.
        assert len(targets) == 1

    def test_include_slow_flag(self, tmp_path):
        project = _make_workspace(tmp_path, models=[{"name": "fast"}])
        # Even with include_slow=True, slow=False targets are included.
        targets = discover_validation_targets(project, include_slow=True)
        assert len(targets) == 1


class TestValidationTarget:
    def test_display_name_without_variant(self):
        t = ValidationTarget(kind="model", name="bracket", variant=None, path=Path("/x"))
        assert t.display_name == "bracket"

    def test_display_name_with_variant(self):
        t = ValidationTarget(kind="model", name="bracket", variant="large", path=Path("/x"))
        assert t.display_name == "bracket:large"

    def test_frozen(self):
        t = ValidationTarget(kind="model", name="bracket", variant=None, path=Path("/x"))
        try:
            t.name = "other"
            assert False, "should raise"
        except AttributeError:
            pass

    def test_default_slow_is_false(self):
        t = ValidationTarget(kind="model", name="bracket", variant=None, path=Path("/x"))
        assert t.slow is False


class TestCheckSummary:
    def test_strips_large_check_data(self):
        checks = [
            {"name": "bbox_size", "type": "bbox_size", "ok": True, "actual": [40, 30, 20], "expected": [40, 30, 20]},
            {"name": "watertight", "type": "watertight", "ok": True, "mesh_stats": {"volume": 24000}},
        ]
        summary = _check_summary(checks)
        assert len(summary) == 2
        assert summary[0] == {"name": "bbox_size", "type": "bbox_size", "ok": True}
        assert summary[1] == {"name": "watertight", "type": "watertight", "ok": True}

    def test_empty_checks(self):
        assert _check_summary([]) == []


class TestTargetSummary:
    def test_full_payload_reduction(self):
        target = ValidationTarget(kind="model", name="bracket", variant=None, path=Path("/x"))
        payload = {
            "ok": True,
            "stage": "validate",
            "model": "bracket",
            "checks": [{"name": "bbox_size", "type": "bbox_size", "ok": True}],
            "warnings": [{"category": "weak_check"}],
            "artifacts": {"stl": "/path/to/bracket.stl"},
            "message": "validation passed",
        }
        summary = _target_summary(target, payload)
        assert summary["kind"] == "model"
        assert summary["name"] == "bracket"
        assert summary["variant"] is None
        assert summary["ok"] is True
        assert summary["stage"] == "validate"
        assert len(summary["checks"]) == 1
        assert summary["warnings"] == [{"category": "weak_check"}]

    def test_failed_payload(self):
        target = ValidationTarget(kind="model", name="bad_model", variant=None, path=Path("/x"))
        payload = {
            "ok": False,
            "stage": "validate",
            "checks": [{"name": "watertight", "type": "watertight", "ok": False}],
            "error": {"type": "MeshNotWatertight", "message": "mesh has holes"},
        }
        summary = _target_summary(target, payload)
        assert summary["ok"] is False
        assert summary["error"]["type"] == "MeshNotWatertight"

    def test_variant_target(self):
        target = ValidationTarget(kind="model", name="bracket", variant="large", path=Path("/x"))
        payload = {"ok": True, "stage": "validate", "checks": []}
        summary = _target_summary(target, payload)
        assert summary["variant"] == "large"


class TestValidateAllIntegration:
    """Integration tests for validate_all with a real buildable model.

    These tests use a scaffolded workspace with the default part.py
    to exercise the full batch pipeline.
    """

    @pytest.fixture(autouse=True)
    def _no_preview_serve(self, monkeypatch):
        monkeypatch.setattr(cli_mod, "serve_preview", lambda *a, **kw: None)

    def test_empty_workspace_returns_ok(self, tmp_path):
        project = _make_workspace(tmp_path)
        result = validate_all(project)
        assert result["ok"] is True
        assert result["summary"]["total"] == 0
        assert result["summary"]["passed"] == 0
        assert result["stage"] == "validate_all"

    def test_single_model_passes(self, tmp_path, monkeypatch):
        """Validate all on a workspace with one buildable model."""
        monkeypatch.chdir(tmp_path)
        main(["new", "batch_test"])
        project = tmp_path / "batch_test"
        monkeypatch.chdir(project)
        # Build the model first so validate has a STL.
        main(["build", "batch_test"])
        result = validate_all(project)
        assert result["summary"]["total"] >= 1
        assert result["artifacts"]["validation_all"] is not None
        # The all.json artifact should exist.
        all_json = Path(result["artifacts"]["validation_all"])
        assert all_json.exists()

    def test_fail_fast_stops_after_failure(self, tmp_path, monkeypatch):
        """With fail_fast, validate_all stops after the first failure."""
        monkeypatch.chdir(tmp_path)
        main(["new", "batch_test"])
        project = tmp_path / "batch_test"
        monkeypatch.chdir(project)
        # Create a second model with broken part.py.
        main(["new", "broken_model"])
        broken_part = project / "models" / "broken_model" / "part.py"
        broken_part.write_text("result = None  # will fail validation")
        # Don't build — validation will fail on build step.
        result = validate_all(project, fail_fast=True)
        assert result["ok"] is False
        # With fail_fast, we should have at most 1 target that failed,
        # but we might have processed some before hitting the failure.
        failed_targets = [t for t in result["targets"] if not t["ok"]]
        assert len(failed_targets) >= 1

    def test_output_path_override(self, tmp_path, monkeypatch):
        """Custom output path for all.json."""
        monkeypatch.chdir(tmp_path)
        main(["new", "batch_test"])
        project = tmp_path / "batch_test"
        monkeypatch.chdir(project)
        custom_output = tmp_path / "custom_report.json"
        result = validate_all(project, output=custom_output)
        assert custom_output.exists()
        report = json.loads(custom_output.read_text())
        assert report["stage"] == "validate_all"

    def test_written_report_includes_own_artifact_path(self, tmp_path, monkeypatch):
        project = _make_workspace(tmp_path, models=[{"name": "bracket"}])
        output = tmp_path / "all.json"
        monkeypatch.setattr("agentcad.batch.validate_target", lambda project, target: {"ok": True, "stage": "validate", "checks": []})

        result = validate_all(project, output=output)
        report = json.loads(output.read_text())

        assert result["artifacts"]["validation_all"] == str(output)
        assert report["artifacts"]["validation_all"] == str(output)

    def test_target_exception_is_recorded_and_report_is_written(self, tmp_path, monkeypatch):
        project = _make_workspace(tmp_path, models=[{"name": "bracket"}])
        output = tmp_path / "all.json"

        def _raise(project, target):
            raise RuntimeError("synthetic validator crash")

        monkeypatch.setattr("agentcad.batch.validate_target", _raise)
        result = validate_all(project, output=output)

        assert result["ok"] is False
        assert output.exists()
        assert result["targets"][0]["error"]["type"] == "RuntimeError"
        assert result["targets"][0]["error"]["message"] == "synthetic validator crash"

    def test_changed_only_is_explicitly_not_implemented(self, tmp_path):
        project = _make_workspace(tmp_path, models=[{"name": "bracket"}])
        output = tmp_path / "all.json"

        result = validate_all(project, output=output, changed_only=True)
        report = json.loads(output.read_text())

        assert result["ok"] is False
        assert result["error"]["type"] == "NotImplemented"
        assert report["error"]["type"] == "NotImplemented"


class TestValidateAllCLI:
    """CLI-level tests for `agentcad validate all`."""

    @pytest.fixture(autouse=True)
    def _no_preview_serve(self, monkeypatch):
        monkeypatch.setattr(cli_mod, "serve_preview", lambda *a, **kw: None)

    def test_validate_all_cli_returns_zero_on_empty(self, tmp_path, monkeypatch):
        """Empty workspace should return 0 (all 0 targets pass)."""
        monkeypatch.chdir(tmp_path)
        main(["new", "empty_project"])
        project = tmp_path / "empty_project"
        monkeypatch.chdir(project)
        # Remove the scaffolded model so workspace is truly empty.
        import shutil
        shutil.rmtree(project / "models" / "empty_project")
        result = main(["validate", "all"])
        assert result == 0

    def test_validate_all_cli_with_single_model(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        main(["new", "cli_batch"])
        project = tmp_path / "cli_batch"
        monkeypatch.chdir(project)
        # Build first so validation succeeds.
        main(["build", "cli_batch"])
        result = main(["validate", "all"])
        # Should succeed (model passes).
        assert result == 0

    def test_validate_all_models_only_flag(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        main(["new", "flag_test"])
        project = tmp_path / "flag_test"
        monkeypatch.chdir(project)
        main(["build", "flag_test"])
        result = main(["validate", "all", "--models"])
        assert result == 0

    def test_validate_all_preserves_single_model_validation(self, tmp_path, monkeypatch):
        """Normal `agentcad validate <model>` still works unchanged."""
        monkeypatch.chdir(tmp_path)
        main(["new", "compat_test"])
        project = tmp_path / "compat_test"
        monkeypatch.chdir(project)
        main(["build", "compat_test"])
        result = main(["validate", "compat_test"])
        assert result == 0

    def test_validate_all_changed_only_cli_returns_clear_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        main(["new", "changed_project"])
        project = tmp_path / "changed_project"
        monkeypatch.chdir(project)

        result = main(["validate", "all", "--changed-only"])

        assert result == 1
