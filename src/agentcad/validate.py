from __future__ import annotations

from pathlib import Path
from typing import Any

from .jsonio import read_json, write_json
from .measure import measure_model
from .render import render_model
from .runner import build_model, utc_now
from .stl import read_stl, section_radius_at_z
from .workspace import model_dir, outputs_dir


def validate_model(project: Path, name: str, render_view: str = "iso") -> dict:
    out_dir = outputs_dir(project, name)
    out_dir.mkdir(parents=True, exist_ok=True)
    validation_path = out_dir / "validation.json"

    build = build_model(project, name)
    if not build.get("ok"):
        payload = _validation_payload(name, [stage_check("build", False, build)], artifacts={"validation": str(validation_path)})
        write_json(validation_path, payload)
        return payload

    measure = measure_model(project, name)
    render = render_model(project, name, render_view)
    checks = [
        stage_check("build", bool(build.get("ok")), build),
        stage_check("measure", bool(measure.get("ok")), measure),
        stage_check("render", bool(render.get("ok")), render),
    ]
    if measure.get("ok"):
        checks.extend(evaluate_feature_coverage(project, name))
        checks.extend(evaluate_design_checks(project, name, measure))

    artifacts = {
        "validation": str(validation_path),
        "build": str(out_dir / "build.json"),
        "geometry": str(out_dir / "geometry.json"),
        "step": str(out_dir / f"{name}.step"),
        "stl": str(out_dir / f"{name}.stl"),
        "preview": str(out_dir / f"preview.{render_view}.svg"),
    }
    payload = _validation_payload(name, checks, artifacts=artifacts)
    write_json(validation_path, payload)
    return payload


def deliver_model(project: Path, name: str, run_validation: bool = True) -> dict:
    out_dir = outputs_dir(project, name)
    out_dir.mkdir(parents=True, exist_ok=True)
    if run_validation:
        validation = validate_model(project, name)
    else:
        validation = read_json(out_dir / "validation.json", default={"ok": False, "message": "validation report missing"})

    artifact_candidates = {
        "step": out_dir / f"{name}.step",
        "stl": out_dir / f"{name}.stl",
        "preview": out_dir / "preview.iso.svg",
        "geometry": out_dir / "geometry.json",
        "validation": out_dir / "validation.json",
        "build": out_dir / "build.json",
    }
    artifacts = {key: str(path) for key, path in artifact_candidates.items() if path.exists()}
    manifest_path = out_dir / "deliverable.json"
    payload = {
        "ok": bool(validation.get("ok")),
        "stage": "deliver",
        "model": name,
        "createdAt": utc_now(),
        "validationOk": bool(validation.get("ok")),
        "artifacts": artifacts,
        "manifest": str(manifest_path),
        "message": "delivery manifest written" if validation.get("ok") else "delivery manifest written with failing validation",
    }
    write_json(manifest_path, payload)
    return payload


def evaluate_design_checks(project: Path, name: str, measure_payload: dict) -> list[dict]:
    design_path = model_dir(project, name) / "design.json"
    design = read_json(design_path, default={}) or {}
    checks = []
    for index, check in enumerate(design.get("checks") or []):
        if not isinstance(check, dict):
            checks.append({"name": f"design[{index}]", "ok": False, "error": "check must be an object"})
            continue
        checks.append(evaluate_check(project, name, check, measure_payload, index))
    return checks


def evaluate_feature_coverage(project: Path, name: str) -> list[dict]:
    design_path = model_dir(project, name) / "design.json"
    design = read_json(design_path, default={}) or {}
    features = design.get("features") or []
    checks = design.get("checks") or []
    check_ids = {str(check.get("id")) for check in checks if isinstance(check, dict) and check.get("id")}
    results = []
    for index, feature in enumerate(features):
        if not isinstance(feature, dict):
            results.append({"name": f"feature_coverage[{index}]", "type": "feature_coverage", "ok": False, "error": "feature must be an object"})
            continue
        feature_id = str(feature.get("id") or f"feature_{index}")
        linked = feature.get("checks") or []
        existing = [check_id for check_id in linked if str(check_id) in check_ids]
        results.append(
            {
                "name": f"feature_coverage:{feature_id}",
                "type": "feature_coverage",
                "ok": bool(existing),
                "feature": feature_id,
                "checks": linked,
                "matchedChecks": existing,
            }
        )
    return results


def evaluate_check(project: Path, name: str, check: dict, measure_payload: dict, index: int) -> dict:
    check_type = str(check.get("type") or f"check_{index}")
    geometry = measure_payload.get("geometry") or {}
    if check_type == "bbox_size":
        expected = check.get("expected")
        tolerance = float(check.get("tolerance", 0.0))
        actual = ((geometry.get("bbox") or {}).get("size"))
        ok = _vec_close(actual, expected, tolerance)
        return {
            "name": check.get("id") or "bbox_size",
            "type": check_type,
            "ok": ok,
            "expected": expected,
            "actual": actual,
            "tolerance": tolerance,
        }
    if check_type == "watertight":
        expected = bool(check.get("expected", True))
        actual = bool((geometry.get("mesh") or {}).get("watertight"))
        return {"name": check.get("id") or "watertight", "type": check_type, "ok": actual == expected, "expected": expected, "actual": actual}
    if check_type == "artifact_exists":
        raw_path = str(check.get("path") or "")
        path = model_dir(project, name) / raw_path
        return {"name": check.get("id") or f"artifact_exists:{raw_path}", "type": check_type, "ok": path.exists(), "path": str(path)}
    if check_type == "metadata_equals":
        metadata_path = model_dir(project, name) / "metadata.json"
        metadata = read_json(metadata_path, default={}) or {}
        path_expr = str(check.get("path") or "")
        expected = check.get("expected")
        actual = _get_path(metadata, path_expr)
        return {
            "name": check.get("id") or f"metadata_equals:{path_expr}",
            "type": check_type,
            "ok": actual == expected,
            "path": path_expr,
            "expected": expected,
            "actual": actual,
            "source": str(metadata_path),
        }
    if check_type == "outer_diameter_at_z":
        return evaluate_section_diameter(project, name, check, diameter_kind="outer")
    if check_type == "inner_diameter_at_z":
        return evaluate_section_diameter(project, name, check, diameter_kind="inner")
    if check_type == "diameter_decreases_along_z":
        return evaluate_diameter_monotonic(project, name, check, direction="decreases")
    if check_type == "min_triangles":
        expected = int(check.get("expected", 0))
        actual = int((geometry.get("mesh") or {}).get("triangles") or 0)
        return {"name": check.get("id") or "min_triangles", "type": check_type, "ok": actual >= expected, "expected": expected, "actual": actual}
    if check_type == "volume_range":
        actual = float((geometry.get("mass_properties") or {}).get("volume") or 0.0)
        minimum = check.get("min")
        maximum = check.get("max")
        ok = True
        if minimum is not None:
            ok = ok and actual >= float(minimum)
        if maximum is not None:
            ok = ok and actual <= float(maximum)
        return {"name": check.get("id") or "volume_range", "type": check_type, "ok": ok, "actual": actual, "min": minimum, "max": maximum}
    return {
        "name": check.get("id") or check_type,
        "type": check_type,
        "ok": False,
        "error": f"unsupported check type: {check_type}",
    }


def evaluate_section_diameter(project: Path, name: str, check: dict, diameter_kind: str) -> dict:
    stl_path = outputs_dir(project, name) / f"{name}.stl"
    z = float(check.get("z"))
    expected = float(check.get("expected"))
    tolerance = float(check.get("tolerance", 0.0))
    center = check.get("center") or [0.0, 0.0]
    section = section_radius_at_z(read_stl(stl_path), z, center=(float(center[0]), float(center[1])))
    key = "diameter_outer_estimate" if diameter_kind == "outer" else "diameter_inner_estimate"
    actual = section.get(key)
    ok = bool(section.get("ok")) and actual is not None and abs(float(actual) - expected) <= tolerance
    return {
        "name": check.get("id") or f"{diameter_kind}_diameter_at_z:{z}",
        "type": f"{diameter_kind}_diameter_at_z",
        "ok": ok,
        "z": z,
        "expected": expected,
        "actual": actual,
        "tolerance": tolerance,
        "section": section,
    }


def evaluate_diameter_monotonic(project: Path, name: str, check: dict, direction: str) -> dict:
    stl_path = outputs_dir(project, name) / f"{name}.stl"
    z_values = check.get("z_values") or []
    if not isinstance(z_values, list) or len(z_values) < 2:
        start, end = check.get("z_range") or [None, None]
        samples = int(check.get("samples", 3))
        if start is None or end is None or samples < 2:
            return {"name": check.get("id") or "diameter_decreases_along_z", "type": "diameter_decreases_along_z", "ok": False, "error": "provide z_values or z_range with at least 2 samples"}
        z_values = [float(start) + (float(end) - float(start)) * i / (samples - 1) for i in range(samples)]
    center = check.get("center") or [0.0, 0.0]
    triangles = read_stl(stl_path)
    sections = [section_radius_at_z(triangles, float(z), center=(float(center[0]), float(center[1]))) for z in z_values]
    diameters = [section.get("diameter_outer_estimate") for section in sections]
    epsilon = float(check.get("epsilon", 0.05))
    ok = all(section.get("ok") for section in sections)
    if direction == "decreases":
        ok = ok and all(float(a) >= float(b) - epsilon for a, b in zip(diameters, diameters[1:]) if a is not None and b is not None)
        ok = ok and float(diameters[0]) > float(diameters[-1]) + epsilon
    return {
        "name": check.get("id") or "diameter_decreases_along_z",
        "type": "diameter_decreases_along_z",
        "ok": ok,
        "z_values": z_values,
        "diameters": diameters,
        "sections": sections,
        "epsilon": epsilon,
    }


def stage_check(name: str, ok: bool, payload: dict) -> dict:
    item = {"name": name, "type": "stage", "ok": ok}
    if not ok:
        item["error"] = payload.get("error") or {"message": payload.get("message")}
    return item


def _validation_payload(name: str, checks: list[dict], artifacts: dict[str, str]) -> dict:
    ok = all(bool(check.get("ok")) for check in checks)
    return {
        "ok": ok,
        "stage": "validate",
        "model": name,
        "validatedAt": utc_now(),
        "checks": checks,
        "artifacts": artifacts,
        "message": "validation passed" if ok else "validation failed",
    }


def _vec_close(actual: Any, expected: Any, tolerance: float) -> bool:
    if not isinstance(actual, list) or not isinstance(expected, list) or len(actual) != len(expected):
        return False
    return all(abs(float(a) - float(e)) <= tolerance for a, e in zip(actual, expected))


def _get_path(payload: Any, path_expr: str) -> Any:
    current = payload
    for segment in path_expr.split("."):
        if not segment:
            continue
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        else:
            return None
    return current
