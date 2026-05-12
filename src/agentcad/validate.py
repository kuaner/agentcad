from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from time import perf_counter
from typing import Any

from .checks import CheckContext, known_types, run_check
from .checks.mesh import _get_path, _vec_close
from .contract import (
    GEOMETRY_CHECK_TYPES,
    evaluate_feature_coverage_dict,
    evaluate_weak_check_warnings_dict,
    validate_design_schema_dict,
    search_params_by_keywords,
)
from .jsonio import read_json, write_json
from .measure import measure_model
from .diff import archive_validation
from .payloads import stage_check
from .preview import write_model_preview
from .render import render_models_multi
from .runner import build_model, utc_now
from .section import AXIS_Z, scan_profile, write_section_svg
from .stl import read_stl
from .workspace import model_dir, outputs_dir, outputs_dir_for_variant, variant_params_path

_DEFAULT_VALIDATE_VIEWS = ["iso", "front", "top", "side", "back"]
_TIMED_STAGES = ("build", "measure", "render", "checks", "preview")

# Backward-compatible aliases for modules/tests importing these constants.
_VALID_CHECK_TYPES = known_types()
_GEOMETRY_CHECK_TYPES = GEOMETRY_CHECK_TYPES


def validate_model(
    project: Path,
    name: str,
    render_view: str = "iso",
    render_views: list[str] | None = None,
    variant: str | None = None,
) -> dict:
    out_dir = outputs_dir_for_variant(project, name, variant)
    out_dir.mkdir(parents=True, exist_ok=True)
    validation_path = out_dir / "validation.json"
    observability_path = out_dir / "observability.json"
    timings: dict[str, float] = {}

    with timed_stage(timings, "build"):
        build = build_model(project, name, variant=variant)
    archive_validation(out_dir)
    if not build.get("ok"):
        timings["totalMs"] = timings.get("buildMs", 0)
        payload = _validation_payload(name, [stage_check("build", False, build)], artifacts={"validation": str(validation_path)}, timings=timings)
        write_json(validation_path, payload)
        return payload

    with timed_stage(timings, "measure"):
        measure = measure_model(project, name, variant=variant)
    views = render_views if render_views is not None else _DEFAULT_VALIDATE_VIEWS
    if render_view != "iso" and render_view not in views:
        views = [render_view] + [v for v in views if v != render_view]
    with timed_stage(timings, "render"):
        multi_render = render_models_multi(project, name, views, variant=variant)

    checks = [
        stage_check("build", bool(build.get("ok")), build),
        stage_check("measure", bool(measure.get("ok")), measure),
        stage_check("render", bool(multi_render.get("ok")), multi_render),
    ]
    warnings: list[dict] = []
    auto_scan: dict = {}
    observability: dict | None = None
    if measure.get("ok"):
        with timed_stage(timings, "checks"):
            schema_errors = validate_design_schema(project, name)
            has_blocking_schema = any(not c.get("ok") for c in schema_errors)
            if schema_errors:
                checks.extend(schema_errors)
            if not has_blocking_schema:
                checks.extend(evaluate_feature_coverage(project, name))
                checks.extend(evaluate_design_checks(project, name, measure, variant=variant))
                warnings = evaluate_weak_check_warnings(project, name)

        stl_path = out_dir / f"{name}.stl"
        if stl_path.exists():
            triangles = read_stl(stl_path)
            scan = scan_profile(triangles, axis=AXIS_Z, samples=16, step_threshold=3.0)
            if scan.get("ok"):
                section_artifacts: dict[str, str] = {}
                section_analysis_artifacts: dict[str, str] = {}
                section_analyses: dict[str, dict] = {}
                for step in scan.get("step_changes", []):
                    z = step["pos"]
                    svg_path = out_dir / f"section.z{z:.2f}.svg"
                    info = write_section_svg(triangles, AXIS_Z, z, svg_path)
                    key = f"section_z{z:.2f}".replace(".", "_")
                    section_artifacts[key] = str(svg_path)
                    if info.get("analysis_json"):
                        section_analysis_artifacts[f"{key}_analysis"] = info["analysis_json"]
                    if info.get("analysis"):
                        section_analyses[key] = info["analysis"]
                scan["section_svgs"] = section_artifacts
                scan["section_analysis_json"] = section_analysis_artifacts
                scan["section_analyses"] = section_analyses
                auto_scan = scan
                observability = _observability_payload(name, measure, multi_render, auto_scan)
                write_json(observability_path, observability)

    artifacts = {
        "validation": str(validation_path),
        "build": str(out_dir / "build.json"),
        "geometry": str(out_dir / "geometry.json"),
        "step": str(out_dir / f"{name}.step"),
        "stl": str(out_dir / f"{name}.stl"),
        **(multi_render.get("artifacts") or {}),
        **(auto_scan.get("section_svgs") or {}),
        **(auto_scan.get("section_analysis_json") or {}),
    }
    if observability:
        artifacts["observability"] = str(observability_path)
    payload = _validation_payload(name, checks, artifacts=artifacts, warnings=warnings or None, auto_scan=auto_scan or None, timings=timings)
    design = read_json(model_dir(project, name) / "design.json", default={}) or {}
    if variant:
        v_params_path = variant_params_path(project, name, variant)
        params = read_json(v_params_path, default={}) or {} if v_params_path.exists() else read_json(model_dir(project, name) / "params.json", default={}) or {}
    else:
        params = read_json(model_dir(project, name) / "params.json", default={}) or {}
    _attach_suggested_fixes(payload.get("checks", []), design, params, name=name)
    write_json(validation_path, payload)
    with timed_stage(timings, "preview"):
        preview = write_model_preview(project, name, validation_payload=payload, geometry_payload=measure, variant=variant)
    if preview.get("ok"):
        payload["artifacts"]["preview_page"] = (preview.get("artifacts") or {}).get("preview_page")
    timings["totalMs"] = sum(timings.get(f"{s}Ms", 0) for s in _TIMED_STAGES)
    write_json(validation_path, payload)
    return payload


def deliver_model(project: Path, name: str, run_validation: bool = True, variant: str | None = None) -> dict:
    out_dir = outputs_dir_for_variant(project, name, variant)
    out_dir.mkdir(parents=True, exist_ok=True)
    validation = validate_model(project, name, variant=variant) if run_validation else read_json(out_dir / "validation.json", default={"ok": False, "message": "validation report missing"})
    deliver_path = out_dir / "deliverable.json"
    preview_candidates = {
        f"preview_{p.stem.split('.')[1]}": str(p)
        for p in sorted(out_dir.glob("preview.*.svg"))
        if len(p.stem.split(".")) > 1
    }
    artifact_candidates = {
        "step": str(out_dir / f"{name}.step"),
        "stl": str(out_dir / f"{name}.stl"),
        "geometry": str(out_dir / "geometry.json"),
        "validation": str(out_dir / "validation.json"),
        "metadata": str(model_dir(project, name) / "metadata.json"),
        "precheck": str(out_dir / "precheck.json"),
        "review": str(out_dir / "review.json"),
        "preview_page": str(out_dir / "preview.html"),
        **preview_candidates,
        "deliverable": str(deliver_path),
    }
    artifacts = {k: v for k, v in artifact_candidates.items() if k == "deliverable" or Path(v).exists()}
    payload = {
        "ok": bool(validation.get("ok")),
        "stage": "deliver",
        "model": name,
        "deliveredAt": utc_now(),
        "artifacts": artifacts,
        "message": "delivery manifest ready" if validation.get("ok") else "delivery blocked: validation failed",
    }
    if not validation.get("ok"):
        payload["error"] = {"type": "ValidationFailed", "message": "validation must pass before delivery"}
    write_json(deliver_path, payload)
    return payload


def evaluate_design_checks(project: Path, name: str, measure_payload: dict, variant: str | None = None) -> list[dict]:
    out_dir = outputs_dir_for_variant(project, name, variant)
    design = read_json(model_dir(project, name) / "design.json", default={}) or {}
    stl_path = out_dir / f"{name}.stl"
    stl_cache: list | None = None
    from .section import SectionCache
    section_cache = SectionCache()

    def get_triangles() -> list:
        nonlocal stl_cache
        if stl_cache is None:
            stl_cache = read_stl(stl_path)
        return stl_cache

    ctx = CheckContext(project=project, name=name, measure=measure_payload, get_triangles=get_triangles, out_dir=out_dir, section_cache=section_cache)
    results: list[dict] = []
    for index, check in enumerate(design.get("checks") or []):
        if not isinstance(check, dict):
            results.append({
                "name": f"design[{index}]",
                "type": "design_check",
                "ok": False,
                "error": {"type": "CheckShapeError", "message": "check must be an object"},
            })
            continue
        results.append(run_check(check, ctx))
    return results


def validate_design_schema(project: Path, name: str) -> list[dict]:
    design = read_json(model_dir(project, name) / "design.json", default=None)
    if design is None or not isinstance(design, dict):
        path = model_dir(project, name) / "design.json"
        if not path.exists():
            return [{"name": "design_schema", "type": "design_schema", "ok": False, "error": f"design.json not found: {path}"}]
        return [{"name": "design_schema", "type": "design_schema", "ok": False, "error": "design.json must be a JSON object"}]
    return validate_design_schema_dict(design)


def evaluate_feature_coverage(project: Path, name: str) -> list[dict]:
    design = read_json(model_dir(project, name) / "design.json", default={}) or {}
    return evaluate_feature_coverage_dict(design)


def evaluate_weak_check_warnings(project: Path, name: str) -> list[dict]:
    design = read_json(model_dir(project, name) / "design.json", default={}) or {}
    return evaluate_weak_check_warnings_dict(design)


def evaluate_check(project: Path, name: str, check: dict, measure_payload: dict, index: int, get_triangles=None, section_cache=None) -> dict:
    ctx = CheckContext(
        project=project,
        name=name,
        measure=measure_payload,
        get_triangles=get_triangles if get_triangles is not None else (lambda: read_stl(outputs_dir(project, name) / f"{name}.stl")),
        out_dir=outputs_dir(project, name),
        section_cache=section_cache,
    )
    if not isinstance(check, dict):
        return {
            "name": f"design[{index}]",
            "type": "design_check",
            "ok": False,
            "error": {"type": "CheckShapeError", "message": "check must be an object"},
        }
    return run_check(check, ctx)


def _validation_payload(
    name: str,
    checks: list[dict],
    artifacts: dict[str, str],
    warnings: list[dict] | None = None,
    auto_scan: dict | None = None,
    timings: dict[str, float] | None = None,
) -> dict:
    ok = all(bool(check.get("ok")) for check in checks)
    payload: dict[str, Any] = {
        "ok": ok,
        "stage": "validate",
        "model": name,
        "validatedAt": utc_now(),
        "checks": checks,
        "artifacts": artifacts,
        "message": "validation passed" if ok else "validation failed",
    }
    if warnings:
        payload["warnings"] = warnings
    if auto_scan:
        payload["auto_scan"] = auto_scan
    if timings:
        payload["timings"] = timings
    return payload


@contextmanager
def timed_stage(timings: dict[str, float], name: str):
    """Record elapsed milliseconds for a named stage."""
    start = perf_counter()
    try:
        yield
    finally:
        timings[f"{name}Ms"] = (perf_counter() - start) * 1000


def _observability_payload(
    name: str,
    measure_payload: dict,
    multi_render: dict,
    auto_scan: dict,
) -> dict:
    section_analyses = auto_scan.get("section_analyses") or {}
    section_summaries = []
    warnings = []
    for key, analysis in section_analyses.items():
        bbox = analysis.get("bbox") or {}
        section_warnings = analysis.get("warnings") or []
        section_summaries.append({
            "key": key,
            "axis": analysis.get("axis"),
            "value": analysis.get("value"),
            "bbox": bbox,
            "segment_count": analysis.get("segment_count"),
            "component_count": analysis.get("component_count"),
            "total_segment_length_mm": analysis.get("total_segment_length_mm"),
            "warnings": section_warnings,
        })
        warnings.extend({"section": key, "warning": warning} for warning in section_warnings)

    max_components = max((s.get("component_count") or 0 for s in section_summaries), default=0)
    return {
        "ok": True,
        "stage": "observe",
        "model": name,
        "observedAt": utc_now(),
        "geometry": measure_payload,
        "previews": multi_render.get("artifacts") or {},
        "scan": auto_scan,
        "section_summaries": section_summaries,
        "summary": {
            "section_count": len(section_summaries),
            "max_component_count": max_components,
            "multi_component_sections": [
                s["key"] for s in section_summaries
                if (s.get("component_count") or 0) > 1
            ],
            "warning_count": len(warnings),
        },
        "warnings": warnings,
    }


def _attach_suggested_fixes(checks: list[dict], design: dict, params: dict, *, name: str = "") -> None:
    check_defs = {str(c.get("id", "")): c for c in (design.get("checks") or []) if isinstance(c, dict)}
    for check in checks:
        if check.get("ok", True):
            continue
        check_id = str(check.get("name", ""))
        check_def = check_defs.get(check_id, {})
        param_ref = check_def.get("param_ref")
        param_candidates = _find_param_candidates(check, params) if isinstance(params, dict) else []
        if param_ref and param_ref in params:
            fix = _param_fix(check, param_ref, params[param_ref])
        else:
            fix = _generic_fix(check, name=name)
        fix["likely_source"] = _likely_source(check)
        fix["next_commands"] = _next_commands(check, name)
        if param_candidates and "param" not in fix:
            fix["param_candidates"] = param_candidates
        check["suggested_fix"] = fix


def _param_fix(check: dict, param_key: str, current_value) -> dict:
    expected = check.get("expected")
    actual = check.get("actual")
    if expected is not None and actual is not None:
        try:
            delta = float(expected) - float(actual)
            if isinstance(current_value, (int, float)):
                suggested = round(current_value + delta, 4)
                if suggested <= 0 or abs(delta) > abs(current_value) * 2:
                    return {
                        "param": param_key,
                        "current": current_value,
                        "suggested": float(expected),
                        "confidence": "low",
                        "reason": f"{check.get('type', 'check')} actual={actual} target={expected}; param '{param_key}' may not control this dimension directly, using target as suggested value",
                    }
                return {
                    "param": param_key,
                    "current": current_value,
                    "suggested": suggested,
                    "confidence": "high",
                    "reason": f"{check.get('type', 'check')} actual={actual} target={expected} delta={delta:.3f}",
                }
        except (TypeError, ValueError):
            pass
    return {
        "param": param_key,
        "current": current_value,
        "reason": f"{check.get('type', 'check')} failed; review param '{param_key}'",
    }


def _generic_fix(check: dict, *, name: str = "") -> dict:
    check_type = check.get("type", "")
    parts = [f"fix {check_type} check '{check.get('name', '')}'"]
    actual = check.get("actual")
    expected = check.get("expected")
    if actual is not None:
        parts.append(f"actual: {actual}")
    if expected is not None:
        parts.append(f"target: {expected}")
    hint = check.get("hint")
    if hint:
        parts.append(hint)
    return {
        "action": "; ".join(parts),
        "evidence": {"type": check_type, "actual": actual, "expected": expected},
    }


# ── Suggested-fix enrichment helpers ────────────────────────────────────────


# Check type → likely source heuristic.
_LIKELY_SOURCE_MAP: dict[str, str] = {
    "inner_diameter_at_z": "geometry",
    "outer_diameter_at_z": "geometry",
    "diameter_decreases_along_z": "geometry",
    "section_component_count": "geometry",
    "hole_accessibility": "geometry",
    "min_wall_thickness": "geometry",
    "feature_position": "geometry",
    "volume_range": "geometry",
    "watertight": "artifact",
    "min_triangles": "artifact",
    "metadata_equals": "artifact",
    "artifact_exists": "artifact",
    "feature_coverage": "contract",
}

# Keywords that suggest a param is related to a check dimension.
_PARAM_KEYWORDS_BY_CHECK_TYPE: dict[str, frozenset[str]] = {
    "bbox_size": frozenset({"width", "depth", "height", "length", "size", "dimension"}),
    "inner_diameter_at_z": frozenset({"diameter", "dia", "hole", "bore", "inner"}),
    "outer_diameter_at_z": frozenset({"diameter", "dia", "outer", "od"}),
    "section_bbox_at_z": frozenset({"width", "depth", "thickness", "wall", "section"}),
    "min_clearance": frozenset({"clearance", "gap", "wall", "tolerance"}),
    "hole_accessibility": frozenset({"diameter", "dia", "hole", "fastener", "screw", "bolt", "tool"}),
    "min_wall_thickness": frozenset({"wall", "thickness", "rib", "boss"}),
}


def _likely_source(check: dict) -> str:
    """Heuristic: what is most likely the source of the failure?

    Returns one of: "geometry", "contract", "artifact", "unknown".
    """
    check_type = check.get("type", "")
    has_actual = check.get("actual") is not None
    if check_type == "bbox_size":
        return "geometry" if has_actual else "contract"
    if check_type == "min_clearance":
        return "contract"
    if check_type == "section_bbox_at_z":
        return "geometry" if has_actual else "contract"
    return _LIKELY_SOURCE_MAP.get(check_type, "unknown")


_SIMPLE_NEXT_COMMANDS: dict[str, str] = {
    "artifact_exists": "agentcad build {name}",
    "watertight": "agentcad build {name} --force",
    "min_triangles": "agentcad measure {name}",
    "feature_coverage": "agentcad suggest-checks {name}",
    "hole_accessibility": "agentcad render {name} --section-z <z>",
    "min_wall_thickness": "agentcad probe {name} --scan --axis <z|x|y>",
    "min_clearance": "agentcad precheck {name}",
    "diameter_decreases_along_z": "agentcad probe {name} --scan --axis z",
    "feature_position": "agentcad inspect {name}",
    "section_component_count": "agentcad measure {name}",
    "volume_range": "agentcad measure {name}",
}


def _next_commands(check: dict, name: str) -> list[str]:
    """Recommended CLI commands to investigate or fix the failure."""
    check_type = check.get("type", "")
    simple_cmd = _SIMPLE_NEXT_COMMANDS.get(check_type)
    if simple_cmd:
        return [simple_cmd.format(name=name)]

    # Check types that need dynamic parameters.
    if check_type == "bbox_size":
        return [f"agentcad measure {name}", f"agentcad render {name} --views iso,front,top"]
    if check_type in ("inner_diameter_at_z", "outer_diameter_at_z"):
        z = check.get("z", check.get("section_z"))
        z_str = str(z) if isinstance(z, (int, float)) else "<z>"
        raw_center = check.get("center", (0, 0))
        cx_val = float(raw_center[0]) if isinstance(raw_center, (list, tuple)) and len(raw_center) > 0 else 0.0
        cy_val = float(raw_center[1]) if isinstance(raw_center, (list, tuple)) and len(raw_center) > 1 else 0.0
        return [
            f"agentcad probe {name} --z {z_str} --cx {cx_val} --cy {cy_val}",
            f"agentcad render {name} --section-z {z_str}",
        ]
    if check_type == "section_bbox_at_z":
        z = check.get("z", check.get("section_z"))
        z_str = str(z) if isinstance(z, (int, float)) else "<z>"
        return [f"agentcad render {name} --section-z {z_str}"]
    return [f"agentcad validate {name}"]


def _find_param_candidates(check: dict, params: dict) -> list[str]:
    """Find params.json keys that might control the failing dimension."""
    check_type = check.get("type", "")
    keywords = _PARAM_KEYWORDS_BY_CHECK_TYPE.get(check_type, frozenset())
    if not keywords:
        return []
    return search_params_by_keywords(params, keywords, max_results=3)


__all__ = [
    "validate_model",
    "deliver_model",
    "validate_design_schema",
    "evaluate_feature_coverage",
    "evaluate_weak_check_warnings",
    "evaluate_design_checks",
    "evaluate_check",
    "stage_check",
    "_vec_close",
    "_get_path",
    "_VALID_CHECK_TYPES",
    "_GEOMETRY_CHECK_TYPES",
    "_attach_suggested_fixes",
]
