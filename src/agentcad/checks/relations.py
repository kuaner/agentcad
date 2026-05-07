from __future__ import annotations

from ..geometry import (
    hole_accessibility_at_z,
    min_clearance_3d,
    min_wall_thickness_at_z,
    parse_shape,
)
from ..section import AXIS_Z, write_section_svg
from . import CheckContext, DESIGN_TIME, POST_BUILD, register_check


@register_check("min_clearance", layer=DESIGN_TIME)
def evaluate_min_clearance(check: dict, ctx: CheckContext) -> dict:
    name = check.get("id") or "min_clearance"
    try:
        shape_a = parse_shape(check.get("feature_a") or check.get("a"))
        shape_b = parse_shape(check.get("feature_b") or check.get("b"))
    except (ValueError, KeyError, TypeError) as exc:
        return {
            "name": name,
            "type": "min_clearance",
            "ok": False,
            "error": {"type": "CheckInputError", "message": f"invalid shape descriptor: {exc}"},
        }
    min_mm = float(check.get("min_mm", 0.0))
    tolerance = float(check.get("tolerance", 0.0))
    result = min_clearance_3d(shape_a, shape_b)
    actual = float(result["clearance_mm"])
    ok = actual >= (min_mm - tolerance)
    payload = {
        "name": name,
        "type": "min_clearance",
        "ok": ok,
        "min_mm": min_mm,
        "tolerance": tolerance,
        "actual_mm": actual,
        "z_overlap_mm": result["z_overlap_mm"],
        "xy_clearance_mm": result["xy_clearance_mm"],
        "interferes": result["interferes"],
    }
    if not ok:
        payload["hint"] = f"shapes interfere or are too close by {min_mm - actual:.3f}mm"
    return payload


@register_check("hole_accessibility", layer=POST_BUILD)
def evaluate_hole_accessibility(check: dict, ctx: CheckContext) -> dict:
    check_id = check.get("id") or "hole_accessibility"
    raw_z = check.get("z")
    raw_center = check.get("center")
    if raw_z is None or raw_center is None:
        return _input_error(check, "hole_accessibility", "check requires 'z' and 'center' fields")
    try:
        cx, cy = float(raw_center[0]), float(raw_center[1])
        if "hole_radius" in check:
            hole_r = float(check["hole_radius"])
        elif "hole_diameter" in check:
            hole_r = float(check["hole_diameter"]) / 2.0
        else:
            raise KeyError("hole_radius or hole_diameter")

        if "clearance_radius" in check:
            clearance_r = float(check["clearance_radius"])
        elif "clearance_diameter" in check:
            clearance_r = float(check["clearance_diameter"]) / 2.0
        else:
            raise KeyError("clearance_radius or clearance_diameter")
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        return _input_error(check, "hole_accessibility", f"invalid hole_accessibility parameters: {exc}")
    if clearance_r <= hole_r:
        return _input_error(check, "hole_accessibility", "clearance_radius must exceed hole_radius")
    triangles = ctx.get_triangles()
    z = float(raw_z)
    result = hole_accessibility_at_z(triangles, z, (cx, cy), hole_r, clearance_r)
    payload = {
        "name": check_id,
        "type": "hole_accessibility",
        "ok": result["ok"],
        "z": z,
        "center": [cx, cy],
        "hole_radius": hole_r,
        "clearance_radius": clearance_r,
        "blocking_point_count": result["blocking_point_count"],
        "min_blocking_radius": result["min_blocking_radius"],
    }
    if not result["ok"]:
        svg_path = ctx.out_dir / f"debug.{check_id}.z{z:.2f}.svg"
        info = write_section_svg(triangles, AXIS_Z, z, svg_path)
        payload["debug_svg"] = info.get("svg")
        payload["hint"] = (
            f"material at radius={result['min_blocking_radius']:.2f}mm blocks "
            f"tool envelope of {clearance_r}mm"
        )
    return payload


@register_check("min_wall_thickness", layer=POST_BUILD)
def evaluate_min_wall_thickness(check: dict, ctx: CheckContext) -> dict:
    check_id = check.get("id") or "min_wall_thickness"
    raw_z = check.get("z")
    if raw_z is None:
        return _input_error(check, "min_wall_thickness", "check requires 'z' field")
    min_mm = float(check.get("min_mm", 0.0))
    tolerance = float(check.get("tolerance", 0.0))
    raw_region = check.get("region")
    region = None
    if raw_region is not None:
        try:
            (x0, y0), (x1, y1) = raw_region[0], raw_region[1]
            region = ((float(x0), float(y0)), (float(x1), float(y1)))
        except (TypeError, IndexError, ValueError):
            return _input_error(check, "min_wall_thickness", "region must be [[x0,y0],[x1,y1]]")
    triangles = ctx.get_triangles()
    z = float(raw_z)
    sample_res = float(check.get("sample_resolution", 0.5))
    result = min_wall_thickness_at_z(triangles, z, region=region, sample_resolution=sample_res)
    if not result.get("ok"):
        return {
            "name": check_id,
            "type": "min_wall_thickness",
            "ok": False,
            "z": z,
            "region": raw_region,
            "error": {"type": "ThicknessError", "message": str(result.get("error"))},
        }
    actual = float(result["min_thickness_mm"])
    ok = actual >= (min_mm - tolerance)
    payload = {
        "name": check_id,
        "type": "min_wall_thickness",
        "ok": ok,
        "z": z,
        "region": raw_region,
        "min_mm": min_mm,
        "tolerance": tolerance,
        "actual_mm": actual,
        "min_pair": result.get("min_pair"),
        "sample_count": result.get("point_count"),
    }
    if not ok:
        svg_path = ctx.out_dir / f"debug.{check_id}.z{z:.2f}.svg"
        info = write_section_svg(triangles, AXIS_Z, z, svg_path)
        payload["debug_svg"] = info.get("svg")
        payload["hint"] = f"thickness {actual:.3f}mm < min {min_mm}mm (tol ±{tolerance})"
    return payload


def _input_error(check: dict, check_type: str, message: str) -> dict:
    return {
        "name": check.get("id") or check_type,
        "type": check_type,
        "ok": False,
        "error": {"type": "CheckInputError", "message": message},
    }
