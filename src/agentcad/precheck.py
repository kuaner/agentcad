"""Static design-time prechecks: solve design.json contracts without building."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .checks import CheckContext, known_types, run_check, static_types
from .contract.evidence import evaluate_feature_coverage
from .contract.schema import validate_design_schema
from .contract.weak import evaluate_weak_check_warnings
from .jsonio import read_json, write_json
from .runner import utc_now
from .workspace import model_dir, outputs_dir


# Check types that can be evaluated without STL (pure design-time compute).
_STATIC_CHECK_TYPES = static_types()
_VALID_CHECK_TYPES = known_types()


def precheck_model(project: Path, name: str) -> dict:
    out_dir = outputs_dir(project, name)
    out_dir.mkdir(parents=True, exist_ok=True)
    precheck_path = out_dir / "precheck.json"

    design_path = model_dir(project, name) / "design.json"
    if not design_path.exists():
        payload = _payload(name, [{
            "name": "design_present",
            "type": "design_present",
            "ok": False,
            "error": {"type": "DesignMissing", "message": f"design.json not found at {design_path}"},
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
        name,
        checks,
        artifacts={"precheck": str(precheck_path)},
        warnings=warnings or None,
        relations=relations or None,
        deferred=deferred or None,
        errors=errors or None,
    )
    write_json(precheck_path, payload)
    return payload


def _evaluate_static_checks(project: Path, name: str) -> tuple[list[dict], list[dict]]:
    design_path = model_dir(project, name) / "design.json"
    design = read_json(design_path, default={}) or {}
    results: list[dict] = []
    errors: list[dict] = []

    def _never_read_stl() -> list:
        raise RuntimeError("static precheck attempted STL access")

    ctx = CheckContext(
        project=project,
        name=name,
        measure={},
        get_triangles=_never_read_stl,
        out_dir=outputs_dir(project, name),
    )

    for index, raw in enumerate(design.get("checks") or []):
        if not isinstance(raw, dict):
            continue
        check_type = str(raw.get("type") or "")
        if check_type not in _STATIC_CHECK_TYPES:
            continue
        result = run_check(raw, ctx)
        if not result.get("ok") and "error" in result:
            errors.append({"index": index, "id": raw.get("id"), "type": check_type, "error": result.get("error")})
        results.append(result)
    return results, errors


def _build_relation_matrix(static_results: list[dict]) -> list[dict]:
    rows = []
    for item in static_results:
        if item.get("type") != "min_clearance":
            continue
        rows.append({
            "id": item.get("name"),
            "ok": item.get("ok"),
            "clearance_mm": item.get("actual_mm"),
            "min_mm": item.get("min_mm"),
            "interferes": item.get("interferes"),
        })
    return rows


def _list_deferred_checks(project: Path, name: str) -> list[dict]:
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
        "precheckedAt": utc_now(),
        "checks": checks,
        "artifacts": artifacts,
        "message": (
            "precheck passed — safe to write part.py"
            if ok
            else "precheck failed — fix design.json or params before writing part.py"
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
