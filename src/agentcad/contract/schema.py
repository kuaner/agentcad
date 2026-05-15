from __future__ import annotations

from pathlib import Path
from typing import Any

from ..checks import known_types
from ..jsonio import read_json
from ..workspace import model_dir
from .common import (
    EVIDENCE_COLUMNS,
    SEVERITIES,
    SchemaIssue,
    _affects_for_failure,
    _feature_ids,
    _feature_refs_for_intent,
    _issue,
    _iter_design_interfaces,
    _iter_failure_modes,
    _num_or_none,
    _required_evidence_from_payload,
    _triple_or_none,
)

def _check_path(index: int, field: str | None = None) -> str:
    return f"checks[{index}]" + (f".{field}" if field else "")


def _feature_path(index: int, field: str | None = None) -> str:
    return f"features[{index}]" + (f".{field}" if field else "")


def _intent_path(section: str, index: int, field: str | None = None) -> str:
    return f"{section}[{index}]" + (f".{field}" if field else "")


def valid_check_types() -> frozenset[str]:
    return known_types()


def load_design(project: Path, name: str) -> tuple[Path, dict[str, Any] | None]:
    path = model_dir(project, name) / "design.json"
    design = read_json(path, default=None)
    return path, design if isinstance(design, dict) else None


def validate_design_schema(project: Path, name: str) -> list[dict]:
    design_path, design = load_design(project, name)
    if not design_path.exists():
        return [_issue("", f"design.json not found: {design_path}").to_check()]
    if design is None:
        return [_issue("", "design.json must be a JSON object").to_check()]
    issues = validate_design_schema_issues(design)
    return [issue.to_check() for issue in issues]


def validate_design_schema_issues(design: dict[str, Any]) -> list[SchemaIssue]:
    """Validate design.json schema and return structured issues with field paths."""
    issues: list[SchemaIssue] = []
    known = valid_check_types()

    # Schema version check.
    schema = design.get("schema")
    if schema is not None and str(schema) not in {
        "agentcad.design-spec.v1",
        "agentcad.design.v1",
        "design-spec.v1",  # legacy prefix-less form used in templates and examples
    }:
        issues.append(_issue(
            "schema",
            f"unsupported schema version: {schema!r}",
            hint="Use 'agentcad.design-spec.v1' or 'design-spec.v1' or remove the schema field.",
        ))

    features = design.get("features")
    if features is not None and not isinstance(features, list):
        issues.append(_issue("features", "'features' must be an array"))
    elif isinstance(features, list):
        seen_feature_ids: set[str] = set()
        for i, feature in enumerate(features):
            if not isinstance(feature, dict):
                issues.append(_issue(_feature_path(i), "feature must be an object"))
            elif not feature.get("id"):
                issues.append(_issue(_feature_path(i, "id"), "missing required 'id' field"))
            else:
                fid = str(feature["id"])
                if fid in seen_feature_ids:
                    issues.append(_issue(_feature_path(i, "id"), f"duplicate feature id: {fid!r}"))
                seen_feature_ids.add(fid)

    checks = design.get("checks")
    if checks is not None and not isinstance(checks, list):
        issues.append(_issue("checks", "'checks' must be an array"))
    elif isinstance(checks, list):
        seen: set[str] = set()
        for i, check in enumerate(checks):
            if not isinstance(check, dict):
                issues.append(_issue(_check_path(i), "check must be an object"))
                continue
            check_id = check.get("id")
            if not check_id:
                issues.append(_issue(_check_path(i, "id"), "missing required 'id' field"))
            else:
                check_id = str(check_id)
                if check_id in seen:
                    issues.append(_issue(_check_path(i, "id"), f"duplicate check id: {check_id!r}"))
                seen.add(check_id)
            check_type = check.get("type")
            if not check_type:
                issues.append(_issue(_check_path(i, "type"), "missing required 'type' field"))
            elif str(check_type) not in known:
                issues.append(_issue(
                    _check_path(i, "type"),
                    f"unknown type {check_type!r}; valid: {sorted(known)}",
                    hint=f"Did you mean one of: {sorted(known)}?",
                ))

            # Check-type-specific schema validation.
            issues.extend(_validate_check_by_type(check, i))

    issues.extend(_validate_design_intent_fields(design))
    return issues


def _validate_design_intent_fields(design: dict[str, Any]) -> list[SchemaIssue]:
    """Validate structured design-intent fields used by review and planners."""
    issues: list[SchemaIssue] = []
    feature_ids = _feature_ids(design)

    surfaces = design.get("functional_surfaces")
    if surfaces is not None:
        if not isinstance(surfaces, list):
            issues.append(_issue("functional_surfaces", "'functional_surfaces' must be an array"))
        else:
            seen: set[str] = set()
            for i, surface in enumerate(surfaces):
                if not isinstance(surface, dict):
                    issues.append(_issue(_intent_path("functional_surfaces", i), "functional surface must be an object"))
                    continue
                sid = surface.get("id")
                if not sid:
                    issues.append(_issue(_intent_path("functional_surfaces", i, "id"), "missing required 'id' field"))
                elif str(sid) in seen:
                    issues.append(_issue(_intent_path("functional_surfaces", i, "id"), f"duplicate functional surface id: {sid!r}"))
                else:
                    seen.add(str(sid))
                fid = surface.get("feature_id")
                if not fid:
                    issues.append(_issue(_intent_path("functional_surfaces", i, "feature_id"), "functional surface requires 'feature_id'"))
                elif feature_ids and str(fid) not in feature_ids:
                    issues.append(_issue(
                        _intent_path("functional_surfaces", i, "feature_id"),
                        f"unknown feature_id: {fid!r}",
                        hint="Reference an existing features[].id.",
                    ))
                normal = surface.get("normal")
                if normal is not None and _triple_or_none(normal) is None:
                    issues.append(_issue(_intent_path("functional_surfaces", i, "normal"), "normal must be [x, y, z] numbers"))

    interfaces_raw = design.get("interfaces")
    if interfaces_raw is not None and not isinstance(interfaces_raw, (list, dict)):
        issues.append(_issue("interfaces", "'interfaces' must be an array or object"))
    for i, interface in enumerate(_iter_design_interfaces(design)):
        if not isinstance(interface, dict):
            issues.append(_issue(_intent_path("interfaces", i), "interface must be an object"))
            continue
        if not interface.get("id"):
            issues.append(_issue(_intent_path("interfaces", i, "id"), "interface requires 'id'"))
        if not interface.get("type"):
            issues.append(_issue(_intent_path("interfaces", i, "type"), "interface requires 'type'"))
        refs = _feature_refs_for_intent(interface)
        if not refs:
            issues.append(_issue(_intent_path("interfaces", i, "feature_ids"), "interface requires feature_ids or feature_id"))
        for fid in refs:
            if feature_ids and fid not in feature_ids:
                issues.append(_issue(
                    _intent_path("interfaces", i, "feature_ids"),
                    f"unknown feature id: {fid!r}",
                    hint="Reference existing features[].id values.",
                ))
        axis = interface.get("access_axis") or interface.get("insertion_axis")
        if axis is not None and str(axis).lower() not in ("x", "y", "z"):
            issues.append(_issue(_intent_path("interfaces", i, "access_axis"), "axis must be x, y, or z"))
        for key in ("clearance_mm", "axis_tolerance_mm"):
            if key in interface and _num_or_none(interface.get(key)) is None:
                issues.append(_issue(_intent_path("interfaces", i, key), f"{key} must be numeric"))

    failure_raw = design.get("failure_modes")
    if failure_raw is not None and not isinstance(failure_raw, (list, dict)):
        issues.append(_issue("failure_modes", "'failure_modes' must be an array or object"))
    for i, failure in enumerate(_iter_failure_modes(design)):
        if not isinstance(failure, dict):
            issues.append(_issue(_intent_path("failure_modes", i), "failure mode must be an object"))
            continue
        if not failure.get("id"):
            issues.append(_issue(_intent_path("failure_modes", i, "id"), "failure mode requires 'id'"))
        if not failure.get("mode"):
            issues.append(_issue(_intent_path("failure_modes", i, "mode"), "failure mode requires 'mode'"))
        severity = str(failure.get("severity", "medium")).lower()
        if severity not in SEVERITIES:
            issues.append(_issue(_intent_path("failure_modes", i, "severity"), f"unknown severity: {severity!r}"))
        affects = _affects_for_failure(failure)
        if not affects:
            issues.append(_issue(_intent_path("failure_modes", i, "affects"), "failure mode requires affects/feature_ids"))
        for fid in affects:
            if feature_ids and fid not in feature_ids:
                issues.append(_issue(
                    _intent_path("failure_modes", i, "affects"),
                    f"unknown affected feature id: {fid!r}",
                    hint="Reference existing features[].id values.",
                ))
        for evidence in _required_evidence_from_payload(failure):
            if evidence not in EVIDENCE_COLUMNS:
                issues.append(_issue(
                    _intent_path("failure_modes", i, "required_evidence"),
                    f"unknown evidence column: {evidence!r}; valid: {list(EVIDENCE_COLUMNS)}",
                ))
    return issues


def _validate_check_by_type(check: dict, index: int) -> list[SchemaIssue]:
    """Run type-specific schema validators on a check entry."""
    check_type = str(check.get("type", ""))
    if check_type == "section_bbox_at_z":
        return _validate_section_bbox_check(check, index)
    if check_type == "min_wall_thickness":
        return _validate_min_wall_thickness_check(check, index)
    return []


def _validate_section_bbox_check(check: dict, index: int) -> list[SchemaIssue]:
    """Validate section_bbox_at_z semantics.

    Void assertions without a region can pass on an empty slice (where
    the STL has no mesh at that Z at all). This is a known false-pass
    pattern, so we warn when region is missing.
    """
    issues: list[SchemaIssue] = []
    expected = check.get("expected", "solid")
    expected_dims = _section_bbox_expected_dimensions(expected)
    expected_str = str(expected).lower() if expected_dims is None else ""
    if expected_dims is None and expected_str not in ("solid", "void"):
        issues.append(_issue(
            _check_path(index, "expected"),
            f"expected must be 'solid', 'void', or [width, depth], got {expected!r}",
            hint="Use expected='solid', expected='void' with a region, or expected=[width, depth] with tolerance.",
        ))
    elif expected_str == "void" and "region" not in check:
        issues.append(_issue(
            _check_path(index, "region"),
            "expected='void' requires region to avoid false passes on empty slices",
            severity="warning",
            hint="Add region [[x0,y0],[x1,y1]] so an empty global slice cannot pass accidentally.",
        ))
    return issues


def _section_bbox_expected_dimensions(expected: object) -> list[float] | None:
    if not isinstance(expected, list | tuple) or len(expected) != 2:
        return None
    try:
        return [float(expected[0]), float(expected[1])]
    except (TypeError, ValueError):
        return None


def _validate_min_wall_thickness_check(check: dict, index: int) -> list[SchemaIssue]:
    """Validate min_wall_thickness schema.

    Supports two modes:
    - Single plane: requires z + region + min_mm
    - Range mode: requires axis + range + region + min_mm (+ optional samples)
    """
    has_single = "z" in check
    has_range = "range" in check and "axis" in check
    if has_single and has_range:
        return [_issue(
            _check_path(index),
            "min_wall_thickness has both z (single plane) and axis+range (range mode); specify only one",
            hint="Remove either 'z' for range mode, or 'axis'+'range' for single-plane mode.",
        )]
    if not has_single and not has_range:
        return [_issue(
            _check_path(index),
            "min_wall_thickness requires z (single plane) or axis+range (range mode)",
            hint="Use {z: 3.0, region: [...], min_mm: N} for single plane, "
                 "or {axis: 'z', range: [0, 10], samples: 6, region: [...], min_mm: N} for range mode.",
        )]
    if has_range:
        axis_val = str(check.get("axis", "z")).lower()
        if axis_val != "z":
            return [_issue(
                _check_path(index, "axis"),
                f"range mode currently only supports axis='z' (got '{axis_val}')",
                hint="Use axis='z' for range mode. Single-plane mode using 'z' field supports any plane implicitly.",
            )]
        rng = check.get("range")
        if not isinstance(rng, list) or len(rng) != 2:
            return [_issue(
                _check_path(index, "range"),
                "range must be [start, end]",
            )]
    return []


def validate_design_schema_dict(design: dict[str, Any]) -> list[dict]:
    """Backward-compatible wrapper that returns dict-shaped schema errors."""
    issues = validate_design_schema_issues(design)
    return [issue.to_check() for issue in issues]
