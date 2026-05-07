"""Static design-time prechecks: solve design.json contracts without building.

This module surfaces design errors *before* the part is built, by running
all geometry checks that are pure-computation (no STL needed).

Currently supported pre-checks:
  - design schema validation (id uniqueness, type validity)
  - feature_coverage (every feature has at least one check)
  - min_clearance (computed from declared shape descriptors)
  - feature-to-check linkage health
  - declared shapes overlap with model declared bbox (sanity)

Anything that needs the actual STL (inner_diameter_at_z, watertight, etc.) is
deferred to ``cad validate``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .geometry import min_clearance_3d, parse_shape, shape_aabb
from .jsonio import read_json, write_json
from .runner import utc_now
from .validate import (
    _VALID_CHECK_TYPES,
    evaluate_feature_coverage,
    evaluate_weak_check_warnings,
    validate_design_schema,
)
from .workspace import model_dir, outputs_dir

# Check types that can be evaluated without STL (pure design-time compute).
_STATIC_CHECK_TYPES = frozenset({
    "min_clearance",
})


def precheck_model(project: Path, name: str) -> dict:
    """Run all design-time prechecks on ``models/<name>``.

    Returns a JSON payload with stage/checks/warnings/artifacts mirroring the
    shape of ``cad validate`` so agents can consume both with the same code path.
    """
    out_dir = outputs_dir(project, name)
    out_dir.mkdir(parents=True, exist_ok=True)
    precheck_path = out_dir / "precheck.json"

    design_dir = model_dir(project, name)
    design_path = design_dir / "design.json"
    if not design_path.exists():
        payload = _payload(name, [{
            "name": "design_present", "type": "design_present", "ok": False,
            "error": f"design.json not found at {design_path}",
        }], artifacts={"precheck": str(precheck_path)})
        write_json(precheck_path, payload)
        return payload

    checks: list[dict] = []
    schema_errors = validate_design_schema(project, name)
    if schema_errors:
        checks.extend(schema_errors)
        payload = _payload(name, checks, artifacts={"precheck": str(precheck_path)})
        write_json(precheck_path, payload)
        return payload

    checks.extend(evaluate_feature_coverage(project, name))
    static_results, errors = _evaluate_static_checks(project, name)
    checks.extend(static_results)

    relations = _build_relation_matrix(static_results)
    warnings = evaluate_weak_check_warnings(project, name)
    deferred = _list_deferred_checks(project, name)

    payload = _payload(
        name, checks,
        artifacts={"precheck": str(precheck_path)},
        warnings=warnings or None,
        relations=relations or None,
        deferred=deferred or None,
        errors=errors or None,
    )
    write_json(precheck_path, payload)
    return payload


def _evaluate_static_checks(project: Path, name: str) -> tuple[list[dict], list[dict]]:
    """Run any check whose evaluation needs only design.json data."""
    design_path = model_dir(project, name) / "design.json"
    design = read_json(design_path, default={}) or {}
    results: list[dict] = []
    errors: list[dict] = []
    for index, raw in enumerate(design.get("checks") or []):
        if not isinstance(raw, dict):
            continue
        check_type = str(raw.get("type") or "")
        if check_type not in _STATIC_CHECK_TYPES:
            continue
        if check_type == "min_clearance":
            results.append(_evaluate_static_min_clearance(raw, index))
    return results, errors


def _evaluate_static_min_clearance(check: dict, index: int) -> dict:
    name = check.get("id") or f"min_clearance[{index}]"
    try:
        shape_a = parse_shape(check.get("feature_a") or check.get("a"))
        shape_b = parse_shape(check.get("feature_b") or check.get("b"))
    except (ValueError, KeyError, TypeError) as exc:
        return {"name": name, "type": "min_clearance", "ok": False,
                "error": f"invalid shape descriptor: {exc}"}
    min_mm = float(check.get("min_mm", 0.0))
    tolerance = float(check.get("tolerance", 0.0))
    result = min_clearance_3d(shape_a, shape_b)
    actual = float(result["clearance_mm"])
    ok = actual >= (min_mm - tolerance)
    payload = {
        "name": name, "type": "min_clearance", "ok": ok,
        "actual_mm": actual,
        "min_mm": min_mm, "tolerance": tolerance,
        "z_overlap_mm": result["z_overlap_mm"],
        "xy_clearance_mm": result["xy_clearance_mm"],
        "interferes": result["interferes"],
    }
    if not ok:
        payload["hint"] = (
            f"shapes interfere by {min_mm - actual:.3f}mm — "
            "fix params before writing part.py"
        )
    return payload


def _build_relation_matrix(static_results: list[dict]) -> list[dict]:
    """Aggregate clearance results into a relations table for review."""
    rows = []
    for r in static_results:
        if r.get("type") != "min_clearance":
            continue
        rows.append({
            "id": r.get("name"),
            "ok": r.get("ok"),
            "clearance_mm": r.get("actual_mm"),
            "min_mm": r.get("min_mm"),
            "interferes": r.get("interferes"),
        })
    return rows


def _list_deferred_checks(project: Path, name: str) -> list[dict]:
    """Report STL-dependent checks that precheck cannot evaluate."""
    design_path = model_dir(project, name) / "design.json"
    design = read_json(design_path, default={}) or {}
    deferred: list[dict] = []
    for raw in design.get("checks") or []:
        if not isinstance(raw, dict):
            continue
        ctype = str(raw.get("type") or "")
        if ctype in _VALID_CHECK_TYPES and ctype not in _STATIC_CHECK_TYPES:
            deferred.append({"id": raw.get("id"), "type": ctype})
    return deferred


def _payload(
    name: str,
    checks: list[dict],
    artifacts: dict[str, str],
    warnings: list[dict] | None = None,
    relations: list[dict] | None = None,
    deferred: list[dict] | None = None,
    errors: list[dict] | None = None,
) -> dict:
    ok = all(bool(c.get("ok")) for c in checks)
    payload: dict[str, Any] = {
        "ok": ok,
        "stage": "precheck",
        "model": name,
        "prechekedAt": utc_now(),
        "checks": checks,
        "artifacts": artifacts,
        "message": (
            "precheck passed — safe to write part.py"
            if ok else
            "precheck failed — fix design.json or params before writing part.py"
        ),
    }
    if warnings:
        payload["warnings"] = warnings
    if relations:
        payload["relations"] = relations
    if deferred:
        payload["deferred_to_validate"] = deferred
    if errors:
        payload["errors"] = errors
    return payload
