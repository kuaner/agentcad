from __future__ import annotations

from pathlib import Path
from typing import Any

from .checks import CheckContext, known_types, run_check
from .checks.mesh import _get_path, _vec_close
from .contract import (
    GEOMETRY_CHECK_TYPES,
    evaluate_feature_coverage_dict,
    evaluate_weak_check_warnings_dict,
    validate_design_schema_dict,
)
from .jsonio import read_json, write_json
from .measure import measure_model
from .payloads import stage_check
from .render import render_models_multi
from .runner import build_model, utc_now
from .section import AXIS_Z, scan_profile, write_section_svg
from .stl import read_stl
from .workspace import model_dir, outputs_dir

_DEFAULT_VALIDATE_VIEWS = ["iso", "back"]

# Backward-compatible aliases for modules/tests importing these constants.
_VALID_CHECK_TYPES = known_types()
_GEOMETRY_CHECK_TYPES = GEOMETRY_CHECK_TYPES


def validate_model(
    project: Path,
    name: str,
    render_view: str = "iso",
    render_views: list[str] | None = None,
) -> dict:
    out_dir = outputs_dir(project, name)
    out_dir.mkdir(parents=True, exist_ok=True)
    validation_path = out_dir / "validation.json"

    build = build_model(project, name)
    if not build.get("ok"):
        payload = _validation_payload(name, [stage_check("build", False, build)], artifacts={"validation": str(validation_path)})
        write_json(validation_path, payload)
        return payload

    measure = measure_model(project, name)
    views = render_views if render_views is not None else _DEFAULT_VALIDATE_VIEWS
    if render_view != "iso" and render_view not in views:
        views = [render_view] + [v for v in views if v != render_view]
    multi_render = render_models_multi(project, name, views)
    primary_render = next((r for r in multi_render.get("results", []) if r.get("ok")), multi_render)

    checks = [
        stage_check("build", bool(build.get("ok")), build),
        stage_check("measure", bool(measure.get("ok")), measure),
        stage_check("render", bool(multi_render.get("ok")), primary_render),
    ]
    warnings: list[dict] = []
    auto_scan: dict = {}
    if measure.get("ok"):
        schema_errors = validate_design_schema(project, name)
        if schema_errors:
            checks.extend(schema_errors)
        else:
            checks.extend(evaluate_feature_coverage(project, name))
            checks.extend(evaluate_design_checks(project, name, measure))
            warnings = evaluate_weak_check_warnings(project, name)

        stl_path = out_dir / f"{name}.stl"
        if stl_path.exists():
            triangles = read_stl(stl_path)
            scan = scan_profile(triangles, axis=AXIS_Z, samples=16, step_threshold=3.0)
            if scan.get("ok"):
                section_artifacts: dict[str, str] = {}
                for step in scan.get("step_changes", []):
                    z = step["pos"]
                    svg_path = out_dir / f"section.z{z:.2f}.svg"
                    write_section_svg(triangles, AXIS_Z, z, svg_path)
                    key = f"section_z{z:.2f}".replace(".", "_")
                    section_artifacts[key] = str(svg_path)
                scan["section_svgs"] = section_artifacts
                auto_scan = scan

    artifacts = {
        "validation": str(validation_path),
        "build": str(out_dir / "build.json"),
        "geometry": str(out_dir / "geometry.json"),
        "step": str(out_dir / f"{name}.step"),
        "stl": str(out_dir / f"{name}.stl"),
        **(multi_render.get("artifacts") or {}),
        **(auto_scan.get("section_svgs") or {}),
    }
    payload = _validation_payload(name, checks, artifacts=artifacts, warnings=warnings or None, auto_scan=auto_scan or None)
    write_json(validation_path, payload)
    return payload


def deliver_model(project: Path, name: str, run_validation: bool = True) -> dict:
    out_dir = outputs_dir(project, name)
    out_dir.mkdir(parents=True, exist_ok=True)
    validation = validate_model(project, name) if run_validation else read_json(out_dir / "validation.json", default={"ok": False, "message": "validation report missing"})
    deliver_path = out_dir / "deliverable.json"
    artifact_candidates = {
        "step": str(out_dir / f"{name}.step"),
        "stl": str(out_dir / f"{name}.stl"),
        "preview": str(out_dir / "preview.iso.svg"),
        "geometry": str(out_dir / "geometry.json"),
        "validation": str(out_dir / "validation.json"),
        "metadata": str(out_dir / "metadata.json"),
        "precheck": str(out_dir / "precheck.json"),
        "review": str(out_dir / "review.json"),
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


def evaluate_design_checks(project: Path, name: str, measure_payload: dict) -> list[dict]:
    design = read_json(outputs_dir(project, name).parent / "design.json", default={}) or {}
    stl_path = outputs_dir(project, name) / f"{name}.stl"
    cache: list | None = None

    def get_triangles() -> list:
        nonlocal cache
        if cache is None:
            cache = read_stl(stl_path)
        return cache

    ctx = CheckContext(project=project, name=name, measure=measure_payload, get_triangles=get_triangles, out_dir=outputs_dir(project, name))
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


def evaluate_check(project: Path, name: str, check: dict, measure_payload: dict, index: int, get_triangles=None) -> dict:
    ctx = CheckContext(
        project=project,
        name=name,
        measure=measure_payload,
        get_triangles=get_triangles if get_triangles is not None else (lambda: read_stl(outputs_dir(project, name) / f"{name}.stl")),
        out_dir=outputs_dir(project, name),
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
    return payload


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
]
