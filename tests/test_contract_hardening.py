"""Tests for contract schema hardening: SchemaIssue, field paths, type-specific validators."""

from __future__ import annotations

from agentcad.contract import (
    SchemaIssue,
    _check_path,
    _feature_path,
    _issue,
    _validate_check_by_type,
    _validate_min_wall_thickness_check,
    _validate_section_bbox_check,
    validate_design_schema_dict,
    validate_design_schema_issues,
)


class TestSchemaIssue:
    def test_to_check_error_severity(self):
        issue = SchemaIssue(path="checks[0].id", message="missing id", severity="error")
        check = issue.to_check()
        assert check["ok"] is False
        assert check["path"] == "checks[0].id"
        assert check["severity"] == "error"
        assert check["error"]["type"] == "SchemaError"
        assert check["error"]["message"] == "missing id"

    def test_to_check_warning_severity(self):
        issue = SchemaIssue(path="checks[2].region", message="void needs region", severity="warning")
        check = issue.to_check()
        assert check["ok"] is True  # warnings don't fail
        assert check["severity"] == "warning"

    def test_to_check_with_hint(self):
        issue = SchemaIssue(path="checks[0].type", message="unknown type", hint="try bbox_size")
        check = issue.to_check()
        assert check["hint"] == "try bbox_size"

    def test_frozen(self):
        issue = SchemaIssue(path="checks[0]", message="error")
        try:
            issue.path = "other"
            assert False, "should raise"
        except AttributeError:
            pass


class TestPathHelpers:
    def test_check_path_with_field(self):
        assert _check_path(3, "region") == "checks[3].region"

    def test_check_path_without_field(self):
        assert _check_path(0) == "checks[0]"

    def test_feature_path_with_field(self):
        assert _feature_path(1, "id") == "features[1].id"

    def test_feature_path_without_field(self):
        assert _feature_path(2) == "features[2]"


class TestValidateDesignSchemaIssues:
    def test_missing_check_id_returns_field_path(self):
        design = {
            "checks": [{"type": "bbox_size"}],
        }
        issues = validate_design_schema_issues(design)
        assert any(i.path == "checks[0].id" for i in issues)

    def test_missing_check_type_returns_field_path(self):
        design = {
            "checks": [{"id": "c1"}],
        }
        issues = validate_design_schema_issues(design)
        assert any(i.path == "checks[0].type" for i in issues)

    def test_unknown_check_type_returns_field_path(self):
        design = {
            "checks": [{"id": "c1", "type": "made_up"}],
        }
        issues = validate_design_schema_issues(design)
        assert any(i.path == "checks[0].type" for i in issues)
        unknown_issues = [i for i in issues if i.path == "checks[0].type"]
        assert unknown_issues[0].hint is not None

    def test_duplicate_check_ids_return_both_locations(self):
        design = {
            "checks": [
                {"id": "dup", "type": "bbox_size"},
                {"id": "dup", "type": "watertight"},
            ],
        }
        issues = validate_design_schema_issues(design)
        dup_issues = [i for i in issues if "duplicate" in i.message]
        assert len(dup_issues) == 1
        assert dup_issues[0].path == "checks[1].id"

    def test_duplicate_feature_ids_return_both_locations(self):
        design = {
            "features": [
                {"id": "dup", "checks": ["c1"]},
                {"id": "dup", "checks": ["c2"]},
            ],
            "checks": [{"id": "c1", "type": "bbox_size"}, {"id": "c2", "type": "watertight"}],
        }
        issues = validate_design_schema_issues(design)
        dup_issues = [i for i in issues if "duplicate" in i.message]
        assert len(dup_issues) == 1
        assert dup_issues[0].path == "features[1].id"

    def test_missing_feature_id_returns_field_path(self):
        design = {
            "features": [{"checks": ["c1"]}],
        }
        issues = validate_design_schema_issues(design)
        assert any(i.path == "features[0].id" for i in issues)

    def test_valid_design_returns_no_issues(self):
        design = {
            "features": [{"id": "f1", "checks": ["c1"]}],
            "checks": [{"id": "c1", "type": "bbox_size"}],
        }
        issues = validate_design_schema_issues(design)
        assert len(issues) == 0

    def test_unsupported_schema_version(self):
        design = {
            "schema": "agentcad.design-spec.v999",
            "features": [],
            "checks": [],
        }
        issues = validate_design_schema_issues(design)
        assert any(i.path == "schema" for i in issues)
        schema_issue = [i for i in issues if i.path == "schema"][0]
        assert schema_issue.hint is not None

    def test_supported_schema_version_passes(self):
        design = {
            "schema": "agentcad.design-spec.v1",
            "features": [],
            "checks": [],
        }
        issues = validate_design_schema_issues(design)
        assert not any(i.path == "schema" for i in issues)

    def test_backward_compatible_dict_output(self):
        design = {
            "checks": [{"type": "bbox_size"}],
        }
        errors = validate_design_schema_dict(design)
        assert isinstance(errors, list)
        assert isinstance(errors[0], dict)
        assert errors[0]["name"] == "design_schema"
        assert errors[0]["ok"] is False
        assert "path" in errors[0]


class TestSectionBboxValidation:
    def test_void_without_region_warns(self):
        check = {"id": "s1", "type": "section_bbox_at_z", "z": 5, "expected": "void"}
        issues = _validate_section_bbox_check(check, 0)
        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert issues[0].path == "checks[0].region"
        assert "region" in issues[0].message

    def test_void_with_region_passes_schema(self):
        check = {
            "id": "s1", "type": "section_bbox_at_z", "z": 5,
            "expected": "void", "region": [[0, 0], [10, 10]],
        }
        issues = _validate_section_bbox_check(check, 0)
        assert len(issues) == 0

    def test_solid_without_region_passes_schema(self):
        check = {"id": "s1", "type": "section_bbox_at_z", "z": 5, "expected": "solid"}
        issues = _validate_section_bbox_check(check, 0)
        assert len(issues) == 0

    def test_dimension_expected_value_passes_schema(self):
        check = {"id": "s1", "type": "section_bbox_at_z", "z": 5, "expected": [10, 8], "tolerance": 0.1}
        issues = _validate_section_bbox_check(check, 0)
        assert len(issues) == 0

    def test_warning_has_hint(self):
        check = {"id": "s1", "type": "section_bbox_at_z", "z": 5, "expected": "void"}
        issues = _validate_section_bbox_check(check, 0)
        assert issues[0].hint is not None
        assert "region" in issues[0].hint

    def test_integrated_in_schema_validation(self):
        design = {
            "checks": [
                {"id": "s1", "type": "section_bbox_at_z", "z": 5, "expected": "void"},
            ],
        }
        issues = validate_design_schema_issues(design)
        assert any(i.path == "checks[0].region" for i in issues)

    def test_invalid_expected_value_errors(self):
        check = {"id": "s1", "type": "section_bbox_at_z", "z": 5, "expected": [10]}
        issues = _validate_section_bbox_check(check, 0)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].path == "checks[0].expected"


class TestMinWallThicknessValidation:
    def test_single_plane_passes(self):
        check = {"id": "w1", "type": "min_wall_thickness", "z": 3.0, "region": [[0, 0], [10, 10]], "min_mm": 1.0}
        issues = _validate_min_wall_thickness_check(check, 0)
        assert len(issues) == 0

    def test_range_mode_passes(self):
        check = {
            "id": "w1", "type": "min_wall_thickness",
            "axis": "z", "range": [0, 10], "samples": 6,
            "region": [[0, 0], [10, 10]], "min_mm": 1.0,
        }
        issues = _validate_min_wall_thickness_check(check, 0)
        assert len(issues) == 0

    def test_missing_both_modes_errors(self):
        check = {"id": "w1", "type": "min_wall_thickness", "region": [[0, 0], [10, 10]], "min_mm": 1.0}
        issues = _validate_min_wall_thickness_check(check, 0)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].hint is not None

    def test_bad_axis_errors(self):
        check = {
            "id": "w1", "type": "min_wall_thickness",
            "axis": "w", "range": [0, 10],
            "region": [[0, 0], [10, 10]], "min_mm": 1.0,
        }
        issues = _validate_min_wall_thickness_check(check, 0)
        assert len(issues) == 1
        assert issues[0].path == "checks[0].axis"

    def test_range_mode_rejects_x_y_axis(self):
        check = {
            "id": "w1", "type": "min_wall_thickness",
            "axis": "x", "range": [0, 10],
            "region": [[0, 0], [10, 10]], "min_mm": 1.0,
        }
        issues = _validate_min_wall_thickness_check(check, 0)
        assert len(issues) == 1
        assert issues[0].path == "checks[0].axis"

    def test_bad_range_shape_errors(self):
        check = {
            "id": "w1", "type": "min_wall_thickness",
            "axis": "z", "range": [0],
            "region": [[0, 0], [10, 10]], "min_mm": 1.0,
        }
        issues = _validate_min_wall_thickness_check(check, 0)
        assert len(issues) == 1
        assert issues[0].path == "checks[0].range"

    def test_integrated_in_schema_validation(self):
        design = {
            "checks": [
                {"id": "w1", "type": "min_wall_thickness", "region": [[0, 0], [10, 10]], "min_mm": 1.0},
            ],
        }
        issues = validate_design_schema_issues(design)
        assert any(i.path == "checks[0]" for i in issues)

    def test_ambiguous_both_modes_errors(self):
        check = {
            "id": "w1", "type": "min_wall_thickness",
            "z": 3.0, "axis": "z", "range": [0, 10],
            "region": [[0, 0], [10, 10]], "min_mm": 1.0,
        }
        issues = _validate_min_wall_thickness_check(check, 0)
        assert len(issues) == 1
        assert "both" in issues[0].message
