from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .checks import known_types
from .jsonio import read_json
from .workspace import model_dir

# Check types that verify actual geometric shape behavior (not only global mesh).
GEOMETRY_CHECK_TYPES = frozenset({
    "outer_diameter_at_z",
    "inner_diameter_at_z",
    "diameter_decreases_along_z",
    "section_bbox_at_z",
    "section_component_count",
    "min_clearance",
    "hole_accessibility",
    "min_wall_thickness",
    "feature_position",
})

# Feature classification keywords.
HOLE_WORDS = frozenset({"hole", "bore", "screw", "bolt", "fastener", "counterbore", "countersink"})
ATTACHMENT_WORDS = frozenset({"rib", "boss", "tab", "lip", "arm", "flange", "hook", "hinge"})
INTERFACE_WORDS = frozenset({"socket", "pin", "dovetail", "gear", "mate", "interface", "neck"})

# Check types that verify hole-specific behavior.
HOLE_CHECK_TYPES = frozenset({"hole_accessibility", "inner_diameter_at_z", "min_clearance"})
# Check types that verify attachment root/interface behavior.
ROOT_CHECK_TYPES = frozenset({"min_wall_thickness", "min_clearance", "feature_position"})

# Evidence dimensions used by review / suggest-checks.  These are deliberately
# coarse: the goal is to catch unmeasured mechanical facts without forcing every
# feature into a heavyweight schema.
POSITION_CHECK_TYPES = frozenset({
    "feature_position",
    "section_bbox_at_z",
    "section_component_count",
    "inner_diameter_at_z",
    "outer_diameter_at_z",
    "min_clearance",
    "hole_accessibility",
})
DIMENSION_CHECK_TYPES = frozenset({
    "bbox_size",
    "inner_diameter_at_z",
    "outer_diameter_at_z",
    "diameter_decreases_along_z",
    "section_bbox_at_z",
    "min_wall_thickness",
    "min_clearance",
})
ACCESS_CHECK_TYPES = frozenset({"hole_accessibility"})
WALL_CHECK_TYPES = frozenset({"min_wall_thickness", "min_clearance"})
INTERFACE_RISK_CHECK_TYPES = frozenset({"min_clearance", "metadata_equals", "hole_accessibility"})

WALL_WORDS = frozenset({"wall", "shell", "thin", "sleeve", "tube", "web", "skin", "rim"})
ROOT_WORDS = frozenset({"root", "base", "interface", "junction", "connected", "attach", "attachment"})


@dataclass(frozen=True)
class SchemaIssue:
    path: str
    message: str
    issue_type: str = "SchemaError"
    severity: str = "error"  # "error" | "warning"
    hint: str | None = None

    def to_check(self, name: str = "design_schema") -> dict:
        payload = {
            "name": name,
            "type": "design_schema",
            "ok": self.severity != "error",
            "path": self.path,
            "severity": self.severity,
            "error": {"type": self.issue_type, "message": self.message},
        }
        if self.hint:
            payload["hint"] = self.hint
        return payload


def _issue(path: str, message: str, *, hint: str | None = None, severity: str = "error") -> SchemaIssue:
    return SchemaIssue(path=path, message=message, hint=hint, severity=severity)


def classify_feature(feature: dict) -> set[str]:
    """Classify a feature by its id, intent, and description text.

    Returns a set of tags: "hole", "load_bearing_attachment", "interface".
    """
    text = " ".join(str(feature.get(k, "")) for k in ("id", "description", "intent")).lower()
    tags: set[str] = set()
    if any(word in text for word in HOLE_WORDS):
        tags.add("hole")
    if any(word in text for word in ATTACHMENT_WORDS):
        tags.add("load_bearing_attachment")
    if any(word in text for word in INTERFACE_WORDS):
        tags.add("interface")
    return tags


def _check_path(index: int, field: str | None = None) -> str:
    return f"checks[{index}]" + (f".{field}" if field else "")


def _feature_path(index: int, field: str | None = None) -> str:
    return f"features[{index}]" + (f".{field}" if field else "")


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
    expected_str = str(expected).lower()
    if expected_str not in ("solid", "void"):
        issues.append(_issue(
            _check_path(index, "expected"),
            f"expected must be 'solid' or 'void', got {expected!r}",
            hint="Use expected='solid' or expected='void' with a region.",
        ))
    elif expected_str == "void" and "region" not in check:
        issues.append(_issue(
            _check_path(index, "region"),
            "expected='void' requires region to avoid false passes on empty slices",
            severity="warning",
            hint="Add region [[x0,y0],[x1,y1]] so an empty global slice cannot pass accidentally.",
        ))
    return issues


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


def evaluate_feature_coverage(project: Path, name: str) -> list[dict]:
    _, design = load_design(project, name)
    return evaluate_feature_coverage_dict(design or {})


def evaluate_feature_coverage_dict(design: dict[str, Any]) -> list[dict]:
    features = design.get("features") or []
    checks = design.get("checks") or []
    check_ids = {str(c.get("id")) for c in checks if isinstance(c, dict) and c.get("id")}
    results: list[dict] = []
    for index, feature in enumerate(features):
        if not isinstance(feature, dict):
            results.append({
                "name": f"feature_coverage[{index}]",
                "type": "feature_coverage",
                "ok": False,
                "error": {"type": "FeatureShapeError", "message": "feature must be an object"},
            })
            continue
        feature_id = str(feature.get("id") or f"feature_{index}")
        linked = feature.get("checks") or []
        matched = [check_id for check_id in linked if str(check_id) in check_ids]
        results.append({
            "name": f"feature_coverage:{feature_id}",
            "type": "feature_coverage",
            "ok": bool(matched),
            "feature": feature_id,
            "checks": linked,
            "matchedChecks": matched,
        })
    return results


def evaluate_feature_evidence_matrix_dict(design: dict[str, Any]) -> list[dict]:
    """Return per-feature evidence coverage across mechanical risk dimensions.

    The matrix is a review aid and gate.  Every feature should prove where it is
    and how large it is.  Access, wall/root, and interface-risk evidence are
    required only when the feature text/classification makes that risk relevant.
    """
    features = design.get("features") or []
    checks = design.get("checks") or []
    check_map = {
        str(c.get("id")): c
        for c in checks
        if isinstance(c, dict) and c.get("id")
    }
    rows: list[dict] = []
    for index, feature in enumerate(features):
        if not isinstance(feature, dict):
            rows.append({
                "feature": f"feature_{index}",
                "ok": False,
                "error": "feature must be an object",
                "missing": ["position", "dimensions"],
            })
            continue
        feature_id = str(feature.get("id") or f"feature_{index}")
        categories = classify_feature(feature)
        linked = _linked_check_defs(feature, check_map)
        required = _feature_evidence_requirements(feature, categories)
        evidence = {
            "position": _evidence_cell(linked, POSITION_CHECK_TYPES, required["position"]),
            "dimensions": _evidence_cell(linked, DIMENSION_CHECK_TYPES, required["dimensions"]),
            "access": _evidence_cell(linked, ACCESS_CHECK_TYPES, required["access"]),
            "wall": _wall_evidence_cell(linked, required["wall"]),
            "interface_risk": _interface_evidence_cell(linked, required["interface_risk"], categories),
        }
        missing = [
            key for key, cell in evidence.items()
            if cell["required"] and not cell["ok"]
        ]
        rows.append({
            "feature": feature_id,
            "categories": sorted(categories) if categories else ["unclassified"],
            "linked_checks": [
                {"id": c.get("id"), "type": c.get("type")}
                for c in linked
            ],
            "evidence": evidence,
            "missing": missing,
            "ok": not missing,
        })
    return rows


def _linked_check_defs(feature: dict[str, Any], check_map: dict[str, dict]) -> list[dict]:
    linked: list[dict] = []
    for check_id in feature.get("checks") or []:
        check = check_map.get(str(check_id))
        if isinstance(check, dict):
            linked.append(check)
    return linked


def _feature_evidence_requirements(feature: dict[str, Any], categories: set[str]) -> dict[str, bool]:
    text = " ".join(str(feature.get(k, "")) for k in ("id", "intent", "description")).lower()
    wall_risk = "load_bearing_attachment" in categories or any(word in text for word in WALL_WORDS)
    interface_risk = "interface" in categories or "hole" in categories
    access_risk = "hole" in categories
    return {
        "position": True,
        "dimensions": True,
        "access": access_risk,
        "wall": wall_risk,
        "interface_risk": interface_risk,
    }


def _evidence_cell(checks: list[dict], accepted_types: frozenset[str], required: bool) -> dict:
    matched = [
        str(check.get("id"))
        for check in checks
        if str(check.get("type", "")) in accepted_types and check.get("id")
    ]
    return {
        "required": required,
        "ok": (not required) or bool(matched),
        "checks": matched,
        "accepted_types": sorted(accepted_types),
    }


def _wall_evidence_cell(checks: list[dict], required: bool) -> dict:
    matched: list[str] = []
    for check in checks:
        check_type = str(check.get("type", ""))
        check_id = str(check.get("id", ""))
        if check_type in WALL_CHECK_TYPES:
            matched.append(check_id)
        elif check_type in ("section_bbox_at_z", "feature_position") and _text_has_any(check_id, ROOT_WORDS):
            matched.append(check_id)
    return {
        "required": required,
        "ok": (not required) or bool(matched),
        "checks": matched,
        "accepted_types": sorted(WALL_CHECK_TYPES | {"section_bbox_at_z", "feature_position"}),
    }


def _interface_evidence_cell(checks: list[dict], required: bool, categories: set[str]) -> dict:
    matched: list[str] = []
    for check in checks:
        check_type = str(check.get("type", ""))
        check_id = str(check.get("id", ""))
        if "hole" in categories:
            if check_type == "min_clearance":
                matched.append(check_id)
        elif check_type in INTERFACE_RISK_CHECK_TYPES:
            matched.append(check_id)
    return {
        "required": required,
        "ok": (not required) or bool(matched),
        "checks": matched,
        "accepted_types": sorted(INTERFACE_RISK_CHECK_TYPES),
    }


def _text_has_any(text: str, words: frozenset[str]) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in words)


def evaluate_weak_check_warnings(project: Path, name: str) -> list[dict]:
    _, design = load_design(project, name)
    return evaluate_weak_check_warnings_dict(design or {})


def evaluate_weak_check_warnings_dict(design: dict[str, Any]) -> list[dict]:
    features = design.get("features") or []
    checks = design.get("checks") or []
    check_type_map = {
        str(c.get("id")): str(c.get("type", ""))
        for c in checks
        if isinstance(c, dict) and c.get("id")
    }
    warnings: list[dict] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        feature_id = str(feature.get("id") or "unknown")
        categories = classify_feature(feature)
        linked_ids = [str(cid) for cid in (feature.get("checks") or [])]

        if not linked_ids:
            warnings.append({
                "feature": feature_id,
                "category": sorted(categories) if categories else ["unclassified"],
                "severity": "blocking",
                "missing": "any_check",
                "message": f"feature '{feature_id}' has no checks linked — add at least one geometry check",
                "hint": "Link outer_diameter_at_z, inner_diameter_at_z, section_bbox_at_z, or min_clearance",
            })
            continue

        linked_types = {check_type_map.get(cid, "") for cid in linked_ids}
        geometry_checks = linked_types & GEOMETRY_CHECK_TYPES
        if not geometry_checks:
            warnings.append({
                "feature": feature_id,
                "category": sorted(categories) if categories else ["unclassified"],
                "severity": "blocking",
                "missing": "geometry_check",
                "linkedCheckTypes": sorted(t for t in linked_types if t),
                "message": f"feature '{feature_id}' has no geometry checks — geometry is not verified",
                "hint": "Use agentcad probe/inspect and add section/diameter/clearance checks",
            })
            continue

        # Category-specific gaps.
        if "hole" in categories:
            hole_checks = linked_types & HOLE_CHECK_TYPES
            if "hole_accessibility" not in hole_checks:
                warnings.append({
                    "feature": feature_id,
                    "category": ["hole"],
                    "severity": "blocking",
                    "missing": "hole_accessibility",
                    "message": f"hole-like feature '{feature_id}' has diameter/clearance checks but no access-envelope check",
                    "hint": "Add hole_accessibility check for the tool/bolt approach direction",
                })

        if "load_bearing_attachment" in categories:
            root_checks = linked_types & ROOT_CHECK_TYPES
            if not root_checks:
                warnings.append({
                    "feature": feature_id,
                    "category": ["load_bearing_attachment"],
                    "severity": "warning",
                    "missing": "root_interface_check",
                    "message": f"load-bearing feature '{feature_id}' has no root/interface check — detachment risk is unverified",
                    "hint": "Add min_wall_thickness at the feature root, or min_clearance at the attachment interface",
                })

    return warnings


def search_params_by_keywords(params: dict, keywords: frozenset | set, max_results: int = 3) -> list[str]:
    """Search params.json keys matching keywords and return matching key names."""
    if not isinstance(params, dict):
        return []
    candidates: list[str] = []
    for key in sorted(params.keys()):
        key_lower = str(key).lower()
        if any(kw in key_lower for kw in keywords):
            candidates.append(str(key))
    return candidates[:max_results]
