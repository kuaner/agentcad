from __future__ import annotations

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
    "min_clearance",
    "hole_accessibility",
    "min_wall_thickness",
    "feature_position",
})


def valid_check_types() -> frozenset[str]:
    return known_types()


def load_design(project: Path, name: str) -> tuple[Path, dict[str, Any] | None]:
    path = model_dir(project, name) / "design.json"
    design = read_json(path, default=None)
    return path, design if isinstance(design, dict) else None


def validate_design_schema(project: Path, name: str) -> list[dict]:
    design_path, design = load_design(project, name)
    if not design_path.exists():
        return [_schema_error(f"design.json not found: {design_path}")]
    if design is None:
        return [_schema_error("design.json must be a JSON object")]
    return validate_design_schema_dict(design)


def validate_design_schema_dict(design: dict[str, Any]) -> list[dict]:
    errors: list[dict] = []
    known = valid_check_types()

    features = design.get("features")
    if features is not None and not isinstance(features, list):
        errors.append(_schema_error("'features' must be an array"))
    elif isinstance(features, list):
        for i, feature in enumerate(features):
            if not isinstance(feature, dict):
                errors.append(_schema_error(f"features[{i}] must be an object"))
            elif not feature.get("id"):
                errors.append(_schema_error(f"features[{i}] missing required 'id' field"))

    checks = design.get("checks")
    if checks is not None and not isinstance(checks, list):
        errors.append(_schema_error("'checks' must be an array"))
    elif isinstance(checks, list):
        seen: set[str] = set()
        for i, check in enumerate(checks):
            if not isinstance(check, dict):
                errors.append(_schema_error(f"checks[{i}] must be an object"))
                continue
            check_id = check.get("id")
            if not check_id:
                errors.append(_schema_error(f"checks[{i}] missing required 'id' field"))
            else:
                check_id = str(check_id)
                if check_id in seen:
                    errors.append(_schema_error(f"checks[{i}] duplicate id: {check_id!r}"))
                seen.add(check_id)
            check_type = check.get("type")
            if not check_type:
                errors.append(_schema_error(f"checks[{i}] (id={check_id!r}) missing required 'type' field"))
            elif str(check_type) not in known:
                errors.append(_schema_error(
                    f"checks[{i}] (id={check_id!r}) unknown type {check_type!r}; valid: {sorted(known)}"
                ))
    return errors


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
        linked_ids = [str(cid) for cid in (feature.get("checks") or [])]
        if not linked_ids:
            warnings.append({
                "feature": feature_id,
                "message": f"feature '{feature_id}' has no checks linked — add at least one geometry check",
                "hint": "Link outer_diameter_at_z, inner_diameter_at_z, section_bbox_at_z, or min_clearance",
            })
            continue
        linked_types = {check_type_map.get(cid, "") for cid in linked_ids}
        geometry_checks = linked_types & GEOMETRY_CHECK_TYPES
        if not geometry_checks:
            warnings.append({
                "feature": feature_id,
                "linkedCheckTypes": sorted(t for t in linked_types if t),
                "message": f"feature '{feature_id}' has no geometry checks — geometry is not verified",
                "hint": "Use cad probe/inspect and add section/diameter/clearance checks",
            })
    return warnings


def _schema_error(message: str) -> dict:
    return {
        "name": "design_schema",
        "type": "design_schema",
        "ok": False,
        "error": message,
    }
