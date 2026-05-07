from __future__ import annotations

from pathlib import Path
from typing import Any

from .geometry import (
    hole_accessibility_at_z,
    min_clearance_3d,
    min_wall_thickness_at_z,
    parse_shape,
)
from .jsonio import read_json, write_json
from .measure import measure_model
from .render import VIEW_DIRS, render_model, render_models_multi
from .runner import build_model, utc_now
from .section import AXIS_Z, scan_profile, write_section_svg
from .stl import read_stl, section_bbox_at_z, section_radius_at_z
from .workspace import model_dir, outputs_dir

_DEFAULT_VALIDATE_VIEWS = ["iso", "back"]

# Check types that verify actual geometric features (section/diameter/bbox).
_GEOMETRY_CHECK_TYPES = frozenset({
    "outer_diameter_at_z",
    "inner_diameter_at_z",
    "diameter_decreases_along_z",
    "section_bbox_at_z",
})


def validate_model(
    project: Path,
    name: str,
    render_view: str = "iso",
    render_views: list[str] | None = None,
) -> dict:
    """Build, measure, render (one or more views), and check design contracts.

    ``render_views`` overrides ``render_view`` when provided. Defaults to
    rendering both ``iso`` and ``back`` views so that back-face features such
    as camera cutouts are always visible in the artifacts.
    """
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
    # Compatibility: pick the primary render result for stage_check
    primary_render = next((r for r in multi_render.get("results", []) if r.get("ok")), multi_render)

    checks = [
        stage_check("build", bool(build.get("ok")), build),
        stage_check("measure", bool(measure.get("ok")), measure),
        stage_check("render", bool(multi_render.get("ok")), primary_render),
    ]
    geometry_warnings: list[dict] = []
    auto_scan: dict = {}
    if measure.get("ok"):
        schema_errors = validate_design_schema(project, name)
        if schema_errors:
            checks.extend(schema_errors)
        else:
            checks.extend(evaluate_feature_coverage(project, name))
            checks.extend(evaluate_design_checks(project, name, measure))
            geometry_warnings = evaluate_weak_check_warnings(project, name)

        # Auto Z-scan: always run, detect step changes, render section SVGs.
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

    preview_artifacts = multi_render.get("artifacts") or {}
    artifacts: dict = {
        "validation": str(validation_path),
        "build": str(out_dir / "build.json"),
        "geometry": str(out_dir / "geometry.json"),
        "step": str(out_dir / f"{name}.step"),
        "stl": str(out_dir / f"{name}.stl"),
        **preview_artifacts,
        **(auto_scan.get("section_svgs") or {}),
    }
    payload = _validation_payload(
        name, checks, artifacts=artifacts,
        warnings=geometry_warnings or None,
        auto_scan=auto_scan or None,
    )
    write_json(validation_path, payload)
    return payload


def deliver_model(project: Path, name: str, run_validation: bool = True) -> dict:
    out_dir = outputs_dir(project, name)
    out_dir.mkdir(parents=True, exist_ok=True)
    if run_validation:
        validation = validate_model(project, name)
    else:
        validation = read_json(out_dir / "validation.json", default={"ok": False, "message": "validation report missing"})

    # Collect all preview SVGs that were rendered (any view).
    preview_svgs = sorted(out_dir.glob("preview.*.svg"))
    preview_candidates = {f"preview_{p.stem.split('.')[1]}": p for p in preview_svgs}

    artifact_candidates = {
        "step": out_dir / f"{name}.step",
        "stl": out_dir / f"{name}.stl",
        "geometry": out_dir / "geometry.json",
        "validation": out_dir / "validation.json",
        "build": out_dir / "build.json",
        **preview_candidates,
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


_VALID_CHECK_TYPES = frozenset({
    "bbox_size",
    "watertight",
    "min_triangles",
    "volume_range",
    "artifact_exists",
    "metadata_equals",
    "outer_diameter_at_z",
    "inner_diameter_at_z",
    "diameter_decreases_along_z",
    "section_bbox_at_z",
    "min_clearance",
    "hole_accessibility",
    "min_wall_thickness",
    "feature_position",
})


def validate_design_schema(project: Path, name: str) -> list[dict]:
    """Validate design.json structure before running checks.

    Returns a list of schema error check-items (ok=False) for any structural
    problems found.  An empty list means the schema is valid.
    """
    design_path = model_dir(project, name) / "design.json"
    if not design_path.exists():
        return [{"name": "design_schema", "type": "design_schema", "ok": False,
                 "error": f"design.json not found: {design_path}"}]

    design = read_json(design_path, default=None)
    if design is None or not isinstance(design, dict):
        return [{"name": "design_schema", "type": "design_schema", "ok": False,
                 "error": "design.json must be a JSON object"}]

    errors: list[dict] = []

    def _err(msg: str) -> None:
        errors.append({"name": "design_schema", "type": "design_schema", "ok": False, "error": msg})

    features = design.get("features")
    if features is not None and not isinstance(features, list):
        _err("'features' must be an array")
    elif isinstance(features, list):
        for i, f in enumerate(features):
            if not isinstance(f, dict):
                _err(f"features[{i}] must be an object")
            elif not f.get("id"):
                _err(f"features[{i}] missing required 'id' field")

    checks = design.get("checks")
    if checks is not None and not isinstance(checks, list):
        _err("'checks' must be an array")
    elif isinstance(checks, list):
        seen_ids: set[str] = set()
        for i, c in enumerate(checks):
            if not isinstance(c, dict):
                _err(f"checks[{i}] must be an object")
                continue
            check_id = c.get("id")
            if not check_id:
                _err(f"checks[{i}] missing required 'id' field")
            else:
                if str(check_id) in seen_ids:
                    _err(f"checks[{i}] duplicate id: {check_id!r}")
                seen_ids.add(str(check_id))
            check_type = c.get("type")
            if not check_type:
                _err(f"checks[{i}] (id={check_id!r}) missing required 'type' field")
            elif check_type not in _VALID_CHECK_TYPES:
                _err(f"checks[{i}] (id={check_id!r}) unknown type {check_type!r}; valid: {sorted(_VALID_CHECK_TYPES)}")

    return errors


def evaluate_design_checks(project: Path, name: str, measure_payload: dict) -> list[dict]:
    design_path = model_dir(project, name) / "design.json"
    design = read_json(design_path, default={}) or {}
    checks = []
    stl_path = outputs_dir(project, name) / f"{name}.stl"
    stl_cache: list | None = None

    def get_triangles() -> list:
        nonlocal stl_cache
        if stl_cache is None:
            stl_cache = read_stl(stl_path)
        return stl_cache

    for index, check in enumerate(design.get("checks") or []):
        if not isinstance(check, dict):
            checks.append({"name": f"design[{index}]", "ok": False, "error": "check must be an object"})
            continue
        checks.append(evaluate_check(project, name, check, measure_payload, index, get_triangles))
    return checks


def evaluate_weak_check_warnings(project: Path, name: str) -> list[dict]:
    """Warn when a feature has no geometry check (section/diameter/bbox).

    These are non-fatal observations: validation still passes, but the agent
    is informed that the feature's geometry is not verified by any meaningful
    check — only by bbox size, watertightness, or similar global metrics.
    """
    design_path = model_dir(project, name) / "design.json"
    design = read_json(design_path, default={}) or {}
    features = design.get("features") or []
    checks = design.get("checks") or []

    check_type_map = {
        str(c.get("id")): str(c.get("type", ""))
        for c in checks
        if isinstance(c, dict) and c.get("id")
    }

    warnings = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        feature_id = str(feature.get("id") or "unknown")
        linked_ids = [str(cid) for cid in (feature.get("checks") or [])]
        if not linked_ids:
            warnings.append({
                "feature": feature_id,
                "message": f"feature '{feature_id}' has no checks linked — add at least one geometry check",
                "hint": "Link outer_diameter_at_z, inner_diameter_at_z, or section_bbox_at_z using the 'checks' field",
            })
            continue
        linked_types = {check_type_map.get(cid, "") for cid in linked_ids}
        geometry_checks = linked_types & _GEOMETRY_CHECK_TYPES
        if not geometry_checks:
            warnings.append({
                "feature": feature_id,
                "linkedCheckTypes": sorted(t for t in linked_types if t),
                "message": f"feature '{feature_id}' has no geometry checks — only trivial checks linked, geometry not verified",
                "hint": "Use 'cad probe <model> --z <z>' to get actual values, then add outer_diameter_at_z or section_bbox_at_z",
            })
    return warnings


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


def evaluate_check(project: Path, name: str, check: dict, measure_payload: dict, index: int, get_triangles=None) -> dict:
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
        return evaluate_section_diameter(project, name, check, diameter_kind="outer", get_triangles=get_triangles)
    if check_type == "inner_diameter_at_z":
        return evaluate_section_diameter(project, name, check, diameter_kind="inner", get_triangles=get_triangles)
    if check_type == "diameter_decreases_along_z":
        return evaluate_diameter_monotonic(project, name, check, direction="decreases", get_triangles=get_triangles)
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
    if check_type == "section_bbox_at_z":
        return evaluate_section_bbox(project, name, check, get_triangles=get_triangles)
    if check_type == "min_clearance":
        return evaluate_min_clearance(check)
    if check_type == "hole_accessibility":
        return evaluate_hole_accessibility(project, name, check, get_triangles=get_triangles)
    if check_type == "min_wall_thickness":
        return evaluate_min_wall_thickness(project, name, check, get_triangles=get_triangles)
    if check_type == "feature_position":
        return evaluate_feature_position(project, name, check, get_triangles=get_triangles)
    return {
        "name": check.get("id") or check_type,
        "type": check_type,
        "ok": False,
        "error": f"unsupported check type: {check_type}",
    }


def evaluate_min_clearance(check: dict) -> dict:
    """Validate that two declared shapes have at least min_mm clearance.

    Pure-geometry check: needs only design.json data, no STL.  This catches
    classic interference errors (hole edge under a wall, hole near board edge,
    hole-to-hole pitch too tight) before the part is even built.
    """
    name = check.get("id") or "min_clearance"
    try:
        shape_a = parse_shape(check.get("feature_a") or check.get("a"))
        shape_b = parse_shape(check.get("feature_b") or check.get("b"))
    except (ValueError, KeyError, TypeError) as exc:
        return {"name": name, "type": "min_clearance", "ok": False,
                "error": f"invalid shape descriptor: {exc}"}
    min_mm = float(check.get("min_mm", 0.0))
    tolerance = float(check.get("tolerance", 0.0))
    result = min_clearance_3d(shape_a, shape_b)
    actual = result["clearance_mm"]
    ok = actual >= (min_mm - tolerance)
    payload = {
        "name": name, "type": "min_clearance", "ok": ok,
        "min_mm": min_mm, "tolerance": tolerance,
        "actual_mm": actual,
        "z_overlap_mm": result["z_overlap_mm"],
        "xy_clearance_mm": result["xy_clearance_mm"],
        "interferes": result["interferes"],
    }
    if not ok:
        payload["hint"] = (
            "shapes interfere or do not meet clearance — check params: "
            f"increase distance by ≥ {min_mm - actual:.3f}mm"
        )
    return payload


def evaluate_hole_accessibility(
    project: Path, name: str, check: dict, get_triangles=None,
) -> dict:
    """Verify a hole is reachable by a tool/bolt of given clearance radius.

    Inputs:
      ``z``: the section plane (e.g., the top face of the base plate)
      ``center``: [cx, cy] — hole centre on that plane
      ``hole_radius``: actual hole radius (mm)
      ``clearance_radius``: tool envelope (mm), e.g., bolt-head outer radius
    Reports OK when no STL material exists between hole_radius and
    clearance_radius at that Z plane.
    """
    check_id = check.get("id") or "hole_accessibility"
    raw_z = check.get("z")
    raw_center = check.get("center")
    if raw_z is None or raw_center is None:
        return {"name": check_id, "type": "hole_accessibility", "ok": False,
                "error": "check requires 'z' and 'center' fields"}
    try:
        cx, cy = float(raw_center[0]), float(raw_center[1])
        hole_r = float(check.get("hole_radius", check.get("hole_diameter", 0)) or 0) \
            or float(check["hole_diameter"]) / 2
        clearance_r = float(check.get("clearance_radius",
                                      check.get("clearance_diameter", 0)) or 0) \
            or float(check["clearance_diameter"]) / 2
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        return {"name": check_id, "type": "hole_accessibility", "ok": False,
                "error": f"invalid hole_accessibility parameters: {exc}"}
    if clearance_r <= hole_r:
        return {"name": check_id, "type": "hole_accessibility", "ok": False,
                "error": "clearance_radius must exceed hole_radius"}
    triangles = get_triangles() if get_triangles is not None else read_stl(
        outputs_dir(project, name) / f"{name}.stl"
    )
    result = hole_accessibility_at_z(triangles, float(raw_z), (cx, cy), hole_r, clearance_r)
    payload = {
        "name": check_id, "type": "hole_accessibility", "ok": result["ok"],
        "z": float(raw_z), "center": [cx, cy],
        "hole_radius": hole_r, "clearance_radius": clearance_r,
        "blocking_point_count": result["blocking_point_count"],
        "min_blocking_radius": result["min_blocking_radius"],
    }
    if not result["ok"]:
        out_dir = outputs_dir(project, name)
        svg_path = out_dir / f"debug.{check_id}.z{float(raw_z):.2f}.svg"
        info = write_section_svg(triangles, AXIS_Z, float(raw_z), svg_path)
        payload["debug_svg"] = info.get("svg")
        payload["hint"] = (
            f"material at radius={result['min_blocking_radius']:.2f}mm blocks "
            f"tool envelope of {clearance_r}mm — move hole or shrink tool"
        )
    return payload


def evaluate_min_wall_thickness(
    project: Path, name: str, check: dict, get_triangles=None,
) -> dict:
    """Spot-check minimum wall thickness at a Z section.

    Optional ``region`` ([[x0,y0],[x1,y1]]) restricts the analysis to a
    rectangle.  Reports min pair distance after near-coincident point
    deduplication.
    """
    check_id = check.get("id") or "min_wall_thickness"
    raw_z = check.get("z")
    if raw_z is None:
        return {"name": check_id, "type": "min_wall_thickness", "ok": False,
                "error": "check requires 'z' field"}
    min_mm = float(check.get("min_mm", 0.0))
    tolerance = float(check.get("tolerance", 0.0))
    raw_region = check.get("region")
    region = None
    if raw_region is not None:
        try:
            (x0, y0), (x1, y1) = raw_region[0], raw_region[1]
            region = ((float(x0), float(y0)), (float(x1), float(y1)))
        except (TypeError, IndexError, ValueError):
            return {"name": check_id, "type": "min_wall_thickness", "ok": False,
                    "error": "region must be [[x0,y0],[x1,y1]]"}
    triangles = get_triangles() if get_triangles is not None else read_stl(
        outputs_dir(project, name) / f"{name}.stl"
    )
    sample_res = float(check.get("sample_resolution", 0.5))
    result = min_wall_thickness_at_z(triangles, float(raw_z), region=region,
                                     sample_resolution=sample_res)
    if not result.get("ok"):
        return {"name": check_id, "type": "min_wall_thickness", "ok": False,
                "z": float(raw_z), "region": raw_region,
                "error": result.get("error")}
    actual = float(result["min_thickness_mm"])
    ok = actual >= (min_mm - tolerance)
    payload = {
        "name": check_id, "type": "min_wall_thickness", "ok": ok,
        "z": float(raw_z), "region": raw_region,
        "min_mm": min_mm, "tolerance": tolerance,
        "actual_mm": actual, "min_pair": result.get("min_pair"),
        "sample_count": result.get("point_count"),
    }
    if not ok:
        out_dir = outputs_dir(project, name)
        svg_path = out_dir / f"debug.{check_id}.z{float(raw_z):.2f}.svg"
        info = write_section_svg(triangles, AXIS_Z, float(raw_z), svg_path)
        payload["debug_svg"] = info.get("svg")
        payload["hint"] = (
            f"thickness {actual:.3f}mm < min {min_mm}mm (tolerance ±{tolerance}); "
            "increase wall_thickness param or move feature"
        )
    return payload


def evaluate_feature_position(
    project: Path, name: str, check: dict, get_triangles=None,
) -> dict:
    """Verify a labelled point is in the expected solid/void state.

    Inputs:
      ``point``: [x, y, z] world-coordinate point
      ``expected``: ``"solid"`` or ``"void"``
      ``tolerance_mm``: optional sample radius for robustness (default 0.0)

    Implementation: read the section at ``z``, check whether any STL
    intersection point lies within ``tolerance_mm`` of (x,y).  Material
    nearby ⇒ solid; clear ⇒ void.
    """
    check_id = check.get("id") or "feature_position"
    raw_point = check.get("point")
    expected = str(check.get("expected", "solid")).lower()
    if raw_point is None or expected not in ("solid", "void"):
        return {"name": check_id, "type": "feature_position", "ok": False,
                "error": "check requires 'point':[x,y,z] and expected='solid'|'void'"}
    try:
        x, y, z = float(raw_point[0]), float(raw_point[1]), float(raw_point[2])
    except (TypeError, IndexError, ValueError):
        return {"name": check_id, "type": "feature_position", "ok": False,
                "error": "'point' must be [x, y, z]"}
    tolerance = float(check.get("tolerance_mm", 0.5))
    triangles = get_triangles() if get_triangles is not None else read_stl(
        outputs_dir(project, name) / f"{name}.stl"
    )
    section = section_bbox_at_z(triangles, z, region=(
        (x - tolerance, y - tolerance), (x + tolerance, y + tolerance)
    ))
    if not section.get("ok"):
        return {"name": check_id, "type": "feature_position", "ok": False,
                "z": z, "point": [x, y, z], "error": section.get("error")}
    has_material = bool(section.get("region_has_points"))
    actual = "solid" if has_material else "void"
    ok = actual == expected
    payload = {
        "name": check_id, "type": "feature_position", "ok": ok,
        "point": [x, y, z], "tolerance_mm": tolerance,
        "expected": expected, "actual": actual,
        "region_point_count": section.get("region_point_count"),
    }
    if not ok:
        out_dir = outputs_dir(project, name)
        svg_path = out_dir / f"debug.{check_id}.z{z:.2f}.svg"
        info = write_section_svg(triangles, AXIS_Z, z, svg_path)
        payload["debug_svg"] = info.get("svg")
    return payload


def evaluate_section_diameter(project: Path, name: str, check: dict, diameter_kind: str, get_triangles=None) -> dict:
    raw_z = check.get("z")
    raw_expected = check.get("expected")
    if raw_z is None or raw_expected is None:
        return {
            "name": check.get("id") or f"{diameter_kind}_diameter_at_z",
            "type": f"{diameter_kind}_diameter_at_z",
            "ok": False,
            "error": "check requires 'z' and 'expected' fields",
        }
    z = float(raw_z)
    expected = float(raw_expected)
    tolerance = float(check.get("tolerance", 0.0))
    center = check.get("center") or [0.0, 0.0]
    triangles = get_triangles() if get_triangles is not None else read_stl(outputs_dir(project, name) / f"{name}.stl")
    section = section_radius_at_z(triangles, z, center=(float(center[0]), float(center[1])))
    key = "diameter_outer_estimate" if diameter_kind == "outer" else "diameter_inner_estimate"
    actual = section.get(key)
    ok = bool(section.get("ok")) and actual is not None and abs(float(actual) - expected) <= tolerance
    result: dict = {
        "name": check.get("id") or f"{diameter_kind}_diameter_at_z:{z}",
        "type": f"{diameter_kind}_diameter_at_z",
        "ok": ok,
        "z": z,
        "expected": expected,
        "actual": actual,
        "tolerance": tolerance,
        "section": section,
    }
    if not ok:
        svg_path = outputs_dir(project, name) / f"debug.{check.get('id') or 'section'}.z{z:.2f}.svg"
        info = write_section_svg(triangles, AXIS_Z, z, svg_path)
        result["debug_svg"] = info.get("svg")
    return result


def evaluate_section_bbox(project: Path, name: str, check: dict, get_triangles=None) -> dict:
    """Check whether a rectangular region at a Z section is solid or void.

    ``expected`` must be ``"solid"`` (intersection points present in region)
    or ``"void"`` (no intersection points in region).
    """
    raw_z = check.get("z")
    if raw_z is None:
        return {"name": check.get("id") or "section_bbox_at_z", "type": "section_bbox_at_z", "ok": False, "error": "check requires 'z' field"}
    expected_state = str(check.get("expected", "solid")).lower()
    if expected_state not in ("solid", "void"):
        return {"name": check.get("id") or "section_bbox_at_z", "type": "section_bbox_at_z", "ok": False, "error": "'expected' must be 'solid' or 'void'"}
    raw_region = check.get("region")
    region = None
    if raw_region is not None:
        try:
            (x0, y0), (x1, y1) = raw_region[0], raw_region[1]
            region = ((float(x0), float(y0)), (float(x1), float(y1)))
        except (TypeError, IndexError, ValueError):
            return {"name": check.get("id") or "section_bbox_at_z", "type": "section_bbox_at_z", "ok": False, "error": "region must be [[x_min,y_min],[x_max,y_max]]"}
    triangles = get_triangles() if get_triangles is not None else read_stl(outputs_dir(project, name) / f"{name}.stl")
    section = section_bbox_at_z(triangles, float(raw_z), region=region)
    if not section.get("ok"):
        return {"name": check.get("id") or "section_bbox_at_z", "type": "section_bbox_at_z", "ok": False, "z": raw_z, "error": section.get("error"), "section": section}
    if region is not None:
        has_points = bool(section.get("region_has_points"))
        ok = (has_points and expected_state == "solid") or (not has_points and expected_state == "void")
        result: dict = {
            "name": check.get("id") or "section_bbox_at_z",
            "type": "section_bbox_at_z",
            "ok": ok,
            "z": float(raw_z),
            "region": raw_region,
            "expected": expected_state,
            "actual": "solid" if has_points else "void",
            "region_point_count": section.get("region_point_count"),
            "section": section,
        }
        if not ok:
            svg_path = outputs_dir(project, name) / f"debug.{check.get('id') or 'section_bbox'}.z{float(raw_z):.2f}.svg"
            info = write_section_svg(triangles, AXIS_Z, float(raw_z), svg_path)
            result["debug_svg"] = info.get("svg")
        return result
    return {"name": check.get("id") or "section_bbox_at_z", "type": "section_bbox_at_z", "ok": True, "z": float(raw_z), "section": section}


def evaluate_diameter_monotonic(project: Path, name: str, check: dict, direction: str, get_triangles=None) -> dict:
    z_values = check.get("z_values") or []
    if not isinstance(z_values, list) or len(z_values) < 2:
        z_range = check.get("z_range")
        if not isinstance(z_range, list) or len(z_range) != 2:
            return {"name": check.get("id") or "diameter_decreases_along_z", "type": "diameter_decreases_along_z", "ok": False, "error": "provide z_values or z_range with at least 2 samples"}
        start, end = z_range
        samples = int(check.get("samples", 3))
        if start is None or end is None or samples < 2:
            return {"name": check.get("id") or "diameter_decreases_along_z", "type": "diameter_decreases_along_z", "ok": False, "error": "provide z_values or z_range with at least 2 samples"}
        z_values = [float(start) + (float(end) - float(start)) * i / (samples - 1) for i in range(samples)]
    center = check.get("center") or [0.0, 0.0]
    triangles = get_triangles() if get_triangles is not None else read_stl(outputs_dir(project, name) / f"{name}.stl")
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


def _validation_payload(
    name: str,
    checks: list[dict],
    artifacts: dict[str, str],
    warnings: list[dict] | None = None,
    auto_scan: dict | None = None,
) -> dict:
    ok = all(bool(check.get("ok")) for check in checks)
    payload: dict = {
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
