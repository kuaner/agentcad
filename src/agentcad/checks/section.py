from __future__ import annotations

from ..section import (
    AXIS_X,
    AXIS_Y,
    AXIS_Z,
    SectionCache,
    analyze_section_segments,
    section_segments,
    write_section_svg,
    AXIS_Z,
    analyze_section_segments,
    section_segments,
    write_section_svg,
)
from ..stl import section_bbox_at_z, section_radius_at_z
from . import CheckContext, POST_BUILD, register_check


def _triangles(ctx: CheckContext):
    return ctx.get_triangles()


def _cached_segments(ctx: CheckContext, axis: int, position: float) -> list:
    """Get section segments from cache if available, otherwise compute directly."""
    triangles = _triangles(ctx)
    cache = ctx.section_cache
    if isinstance(cache, SectionCache):
        return cache.segments(triangles, axis, position)
    return section_segments(triangles, axis, position)


def _cached_analysis(ctx: CheckContext, axis: int, position: float) -> dict:
    """Get section analysis from cache if available, otherwise compute directly."""
    triangles = _triangles(ctx)
    cache = ctx.section_cache
    if isinstance(cache, SectionCache):
        return cache.analysis(triangles, axis, position)
    segs = section_segments(triangles, axis, position)
    return analyze_section_segments(segs, axis, position)


_AXIS_BY_NAME = {"x": AXIS_X, "y": AXIS_Y, "z": AXIS_Z}


@register_check("outer_diameter_at_z", layer=POST_BUILD)
def evaluate_outer_diameter_at_z(check: dict, ctx: CheckContext) -> dict:
    return _evaluate_section_diameter(check, ctx, diameter_kind="outer")


@register_check("inner_diameter_at_z", layer=POST_BUILD)
def evaluate_inner_diameter_at_z(check: dict, ctx: CheckContext) -> dict:
    return _evaluate_section_diameter(check, ctx, diameter_kind="inner")


@register_check("diameter_decreases_along_z", layer=POST_BUILD)
def evaluate_diameter_decreases_along_z(check: dict, ctx: CheckContext) -> dict:
    z_values = check.get("z_values") or []
    if not isinstance(z_values, list) or len(z_values) < 2:
        z_range = check.get("z_range")
        if not isinstance(z_range, list) or len(z_range) != 2:
            return {
                "name": check.get("id") or "diameter_decreases_along_z",
                "type": "diameter_decreases_along_z",
                "ok": False,
                "error": {"type": "CheckInputError", "message": "provide z_values or z_range with at least 2 samples"},
            }
        start, end = z_range
        samples = int(check.get("samples", 3))
        if start is None or end is None or samples < 2:
            return {
                "name": check.get("id") or "diameter_decreases_along_z",
                "type": "diameter_decreases_along_z",
                "ok": False,
                "error": {"type": "CheckInputError", "message": "provide z_values or z_range with at least 2 samples"},
            }
        z_values = [float(start) + (float(end) - float(start)) * i / (samples - 1) for i in range(samples)]
    center = check.get("center") or [0.0, 0.0]
    triangles = _triangles(ctx)
    sections = [section_radius_at_z(triangles, float(z), center=(float(center[0]), float(center[1]))) for z in z_values]
    diameters = [section.get("diameter_outer_estimate") for section in sections]
    epsilon = float(check.get("epsilon", 0.05))
    section_ok = all(section.get("ok") for section in sections)
    has_missing = any(d is None for d in diameters)
    ok = section_ok and not has_missing
    if ok:
        ok = ok and all(float(a) >= float(b) - epsilon for a, b in zip(diameters, diameters[1:]))
        ok = ok and float(diameters[0]) > float(diameters[-1]) + epsilon
    return {
        "name": check.get("id") or "diameter_decreases_along_z",
        "type": "diameter_decreases_along_z",
        "ok": ok,
        "z_values": z_values,
        "diameters": diameters,
        "sections": sections,
        "epsilon": epsilon,
        **({"error": {"type": "SectionSamplingError", "message": "failed to sample one or more z sections"}} if not section_ok or has_missing else {}),
    }


@register_check("section_bbox_at_z", layer=POST_BUILD)
def evaluate_section_bbox_at_z(check: dict, ctx: CheckContext) -> dict:
    raw_z = check.get("z")
    if raw_z is None:
        return _input_error(check, "section_bbox_at_z", "check requires 'z' field")
    expected_state = str(check.get("expected", "solid")).lower()
    if expected_state not in ("solid", "void"):
        return _input_error(check, "section_bbox_at_z", "'expected' must be 'solid' or 'void'")
    raw_region = check.get("region")
    if expected_state == "void" and raw_region is None:
        return _input_error(check, "section_bbox_at_z", "expected='void' requires 'region' to avoid global false-pass")
    region = None
    if raw_region is not None:
        try:
            (x0, y0), (x1, y1) = raw_region[0], raw_region[1]
            region = ((float(x0), float(y0)), (float(x1), float(y1)))
        except (TypeError, IndexError, ValueError):
            return _input_error(check, "section_bbox_at_z", "region must be [[x_min,y_min],[x_max,y_max]]")
    triangles = _triangles(ctx)
    z = float(raw_z)
    section = section_bbox_at_z(triangles, z, region=region)
    if not section.get("ok"):
        return {
            "name": check.get("id") or "section_bbox_at_z",
            "type": "section_bbox_at_z",
            "ok": False,
            "z": z,
            "error": {"type": "SectionError", "message": str(section.get("error"))},
            "section": section,
        }
    if region is None:
        return {"name": check.get("id") or "section_bbox_at_z", "type": "section_bbox_at_z", "ok": True, "z": z, "section": section}
    has_points = bool(section.get("region_has_points"))
    ok = (has_points and expected_state == "solid") or (not has_points and expected_state == "void")
    result = {
        "name": check.get("id") or "section_bbox_at_z",
        "type": "section_bbox_at_z",
        "ok": ok,
        "z": z,
        "region": raw_region,
        "expected": expected_state,
        "actual": "solid" if has_points else "void",
        "region_point_count": section.get("region_point_count"),
        "section": section,
    }
    if not ok:
        svg_path = ctx.out_dir / f"debug.{check.get('id') or 'section_bbox'}.z{z:.2f}.svg"
        info = write_section_svg(triangles, AXIS_Z, z, svg_path)
        result["debug_svg"] = info.get("svg")
        result["debug_analysis_json"] = info.get("analysis_json")
    return result


@register_check("section_component_count", layer=POST_BUILD)
def evaluate_section_component_count(check: dict, ctx: CheckContext) -> dict:
    check_id = check.get("id") or "section_component_count"
    axis_name = str(check.get("axis", "z")).lower()
    axis = _AXIS_BY_NAME.get(axis_name)
    if axis is None:
        return _input_error(check, "section_component_count", "axis must be 'x', 'y', or 'z'")
    raw_position = check.get("position", check.get(axis_name))
    if raw_position is None:
        return _input_error(check, "section_component_count", f"check requires '{axis_name}' or 'position'")
    if check.get("expected") is None:
        return _input_error(check, "section_component_count", "check requires 'expected' component count")

    position = float(raw_position)
    expected = int(check["expected"])
    tolerance = int(check.get("tolerance", 0))
    segs = _cached_segments(ctx, axis, position)
    analysis = _cached_analysis(ctx, axis, position)
    actual = int(analysis.get("component_count", 0))
    ok = abs(actual - expected) <= tolerance
    payload = {
        "name": check_id,
        "type": "section_component_count",
        "ok": ok,
        "axis": axis_name,
        "position": position,
        "expected": expected,
        "actual": actual,
        "tolerance": tolerance,
        "analysis": analysis,
    }
    if not ok:
        svg_path = ctx.out_dir / f"debug.{check_id}.{axis_name}{position:.2f}.svg"
        info = write_section_svg(triangles, axis, position, svg_path)
        payload["debug_svg"] = info.get("svg")
        payload["debug_analysis_json"] = info.get("analysis_json")
    return payload


@register_check("feature_position", layer=POST_BUILD)
def evaluate_feature_position(check: dict, ctx: CheckContext) -> dict:
    check_id = check.get("id") or "feature_position"
    raw_point = check.get("point")
    expected = str(check.get("expected", "solid")).lower()
    if raw_point is None or expected not in ("solid", "void"):
        return _input_error(check, "feature_position", "check requires 'point':[x,y,z] and expected='solid'|'void'")
    try:
        x, y, z = float(raw_point[0]), float(raw_point[1]), float(raw_point[2])
    except (TypeError, IndexError, ValueError):
        return _input_error(check, "feature_position", "'point' must be [x, y, z]")
    tolerance = float(check.get("tolerance_mm", 0.5))
    triangles = _triangles(ctx)
    section = section_bbox_at_z(triangles, z, region=((x - tolerance, y - tolerance), (x + tolerance, y + tolerance)))
    if not section.get("ok"):
        return {
            "name": check_id,
            "type": "feature_position",
            "ok": False,
            "z": z,
            "point": [x, y, z],
            "error": {"type": "SectionError", "message": str(section.get("error"))},
        }
    has_material = bool(section.get("region_has_points"))
    actual = "solid" if has_material else "void"
    ok = actual == expected
    payload = {
        "name": check_id,
        "type": "feature_position",
        "ok": ok,
        "point": [x, y, z],
        "tolerance_mm": tolerance,
        "expected": expected,
        "actual": actual,
        "region_point_count": section.get("region_point_count"),
    }
    if not ok:
        svg_path = ctx.out_dir / f"debug.{check_id}.z{z:.2f}.svg"
        info = write_section_svg(triangles, AXIS_Z, z, svg_path)
        payload["debug_svg"] = info.get("svg")
        payload["debug_analysis_json"] = info.get("analysis_json")
    return payload


def _evaluate_section_diameter(check: dict, ctx: CheckContext, diameter_kind: str) -> dict:
    raw_z = check.get("z")
    raw_expected = check.get("expected")
    if raw_z is None or raw_expected is None:
        return _input_error(check, f"{diameter_kind}_diameter_at_z", "check requires 'z' and 'expected' fields")
    z = float(raw_z)
    expected = float(raw_expected)
    tolerance = float(check.get("tolerance", 0.0))
    center = check.get("center") or [0.0, 0.0]
    triangles = _triangles(ctx)
    section = section_radius_at_z(triangles, z, center=(float(center[0]), float(center[1])))
    key = "diameter_outer_estimate" if diameter_kind == "outer" else "diameter_inner_estimate"
    actual = section.get(key)
    ok = bool(section.get("ok")) and actual is not None and abs(float(actual) - expected) <= tolerance
    result = {
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
        svg_path = ctx.out_dir / f"debug.{check.get('id') or 'section'}.z{z:.2f}.svg"
        info = write_section_svg(triangles, AXIS_Z, z, svg_path)
        result["debug_svg"] = info.get("svg")
        result["debug_analysis_json"] = info.get("analysis_json")
    return result


def _input_error(check: dict, check_type: str, message: str) -> dict:
    return {
        "name": check.get("id") or check_type,
        "type": check_type,
        "ok": False,
        "error": {"type": "CheckInputError", "message": message},
    }
