from __future__ import annotations

from typing import Any

from .types import SuggestContext

def _bbox_shape(ctx: SuggestContext) -> dict[str, Any] | None:
    bbox = ((ctx.geometry.get("geometry") or {}).get("bbox") or {}) if isinstance(ctx.geometry, dict) else {}
    mn = bbox.get("min")
    mx = bbox.get("max")
    if isinstance(mn, list) and isinstance(mx, list) and len(mn) >= 3 and len(mx) >= 3:
        try:
            return {
                "type": "box",
                "x_range": [float(mn[0]), float(mx[0])],
                "y_range": [float(mn[1]), float(mx[1])],
                "z_range": [float(mn[2]), float(mx[2])],
            }
        except (TypeError, ValueError):
            pass
    dims = _bbox_expected_from_params(ctx.params)
    if dims:
        x, y, z = [float(v) for v in dims]
        return {
            "type": "box",
            "x_range": [-x / 2.0, x / 2.0],
            "y_range": [-y / 2.0, y / 2.0],
            "z_range": [0.0, z],
        }
    return None


def _edge_guard_shape(ctx: SuggestContext, center: list[float] | tuple[float, float]) -> dict[str, Any] | None:
    bbox = _bbox_shape(ctx)
    if not bbox:
        return None
    parsed_center = _pair(center)
    if parsed_center is None:
        return None
    cx, cy = parsed_center
    x0, x1 = bbox["x_range"]
    y0, y1 = bbox["y_range"]
    z_range = bbox["z_range"]
    distances = {
        "left": abs(cx - x0),
        "right": abs(x1 - cx),
        "front": abs(cy - y0),
        "back": abs(y1 - cy),
    }
    edge = min(distances, key=distances.get)
    guard = float(_num(_clearance_min(ctx)) or 0.0)
    guard = max(guard, 0.5)
    if edge == "left":
        return {"type": "box", "role": "edge_guard", "x_range": [x0 - guard, x0], "y_range": [y0, y1], "z_range": z_range}
    if edge == "right":
        return {"type": "box", "role": "edge_guard", "x_range": [x1, x1 + guard], "y_range": [y0, y1], "z_range": z_range}
    if edge == "front":
        return {"type": "box", "role": "edge_guard", "x_range": [x0, x1], "y_range": [y0 - guard, y0], "z_range": z_range}
    return {"type": "box", "role": "edge_guard", "x_range": [x0, x1], "y_range": [y1, y1 + guard], "z_range": z_range}


def _feature_z_range(ctx: SuggestContext, feature: dict[str, Any], linked_checks: list[dict[str, Any]]) -> list[float] | None:
    return _feature_axis_range(ctx, feature, linked_checks, "z", fallback_position=_best_z(ctx))


def _feature_axis_range(
    ctx: SuggestContext,
    feature: dict[str, Any],
    linked_checks: list[dict[str, Any]],
    axis: str,
    fallback_position: float | None = None,
) -> list[float] | None:
    key = f"{axis}_range"
    for check in linked_checks:
        for shape_key in ("feature_a", "feature_b", "a", "b"):
            shape = check.get(shape_key)
            if isinstance(shape, dict) and shape.get(key):
                rng = _range(shape.get(key))
                if rng:
                    return rng
    bbox = _bbox_shape(ctx)
    if bbox and bbox.get(key):
        rng = _range(bbox.get(key))
        if rng:
            return rng
    pos = _num(fallback_position)
    if pos is None:
        return None
    thickness = _num(_find_param_hint(ctx.params, {"thickness", "height", "depth"})) or 2.0
    half = max(float(thickness) / 2.0, 0.5)
    return [round(pos - half, 4), round(pos + half, 4)]


def _feature_region(ctx: SuggestContext, feature: dict[str, Any]) -> list[list[float]] | str:
    bbox = _bbox_shape(ctx)
    if bbox:
        x0, x1 = [float(v) for v in bbox["x_range"]]
        y0, y1 = [float(v) for v in bbox["y_range"]]
        inset = 0.25
        if (x1 - x0) > inset * 4 and (y1 - y0) > inset * 4:
            return [[round(x0 + inset, 4), round(y0 + inset, 4)], [round(x1 - inset, 4), round(y1 - inset, 4)]]
        return [[round(x0, 4), round(y0, 4)], [round(x1, 4), round(y1, 4)]]
    return [["<x0>", "<y0>"], ["<x1>", "<y1>"]]


def _best_z(ctx: SuggestContext) -> float | str:
    for source in (
        (ctx.validation.get("auto_scan") or {}).get("step_changes") if isinstance(ctx.validation, dict) else None,
        (ctx.observability.get("scan") or {}).get("step_changes") if isinstance(ctx.observability, dict) else None,
        (ctx.geometry.get("structure") or {}).get("step_changes") if isinstance(ctx.geometry, dict) else None,
    ):
        if isinstance(source, list):
            for step in source:
                if isinstance(step, dict) and _num(step.get("pos")) is not None:
                    return round(float(step["pos"]), 4)
    bbox = ((ctx.geometry.get("geometry") or {}).get("bbox") or {}) if isinstance(ctx.geometry, dict) else {}
    center = bbox.get("center")
    if isinstance(center, list) and len(center) >= 3 and _num(center[2]) is not None:
        return round(float(center[2]), 4)
    for key in ("height", "thickness", "plate_thickness", "wall_thickness"):
        value = _num(ctx.params.get(key))
        if value is not None:
            return round(value / 2.0, 4)
    return "<z>"


def _best_center(ctx: SuggestContext) -> list[float] | list[str]:
    bbox = ((ctx.geometry.get("geometry") or {}).get("bbox") or {}) if isinstance(ctx.geometry, dict) else {}
    center = bbox.get("center")
    if isinstance(center, list) and len(center) >= 2 and _num(center[0]) is not None and _num(center[1]) is not None:
        return [round(float(center[0]), 4), round(float(center[1]), 4)]
    x = _num(ctx.params.get("center_x")) or _num(ctx.params.get("cx"))
    y = _num(ctx.params.get("center_y")) or _num(ctx.params.get("cy"))
    if x is not None and y is not None:
        return [x, y]
    return ["<x>", "<y>"]


def _bbox_expected_from_params(params: dict[str, Any]) -> list[float] | None:
    if not isinstance(params, dict):
        return None
    x = _first_numeric_param(params, ("length", "width", "outer_width", "x_size", "x"))
    y = _first_numeric_param(params, ("depth", "width", "outer_depth", "y_size", "y"))
    z = _first_numeric_param(params, ("height", "thickness", "z_size", "z"))
    if x is None or y is None or z is None:
        return None
    return [x, y, z]


def _bbox_expected_from_geometry(geometry: dict[str, Any]) -> list[float] | None:
    bbox = ((geometry.get("geometry") or {}).get("bbox") or {}) if isinstance(geometry, dict) else {}
    size = bbox.get("size")
    if isinstance(size, list) and len(size) == 3:
        try:
            return [round(float(v), 4) for v in size]
        except (TypeError, ValueError):
            return None
    return None


def _first_numeric_param(params: dict[str, Any], names: tuple[str, ...]) -> float | None:
    lower = {str(k).lower(): v for k, v in params.items()}
    for name in names:
        if name in lower and _num(lower[name]) is not None:
            return float(lower[name])
    for key, value in params.items():
        key_lower = str(key).lower()
        if any(name in key_lower for name in names) and _num(value) is not None:
            return float(value)
    return None


def _clearance_min(ctx: SuggestContext) -> str | float:
    hint = _find_param_hint(ctx.params, {"edge_clearance", "wall_clearance", "min_clearance", "clearance", "gap"})
    return hint or 0.0


def _tolerance(ctx: SuggestContext, default: float | None = 0.5) -> float | None:
    for key in ("tolerance", "tol", "print_tolerance"):
        value = _num(ctx.params.get(key))
        if value is not None:
            return value
    return default


def _axis_position_and_center(axis: str, point: tuple[float, float, float]) -> tuple[float, tuple[float, float]]:
    x, y, z = point
    if axis == "x":
        return x, (y, z)
    if axis == "y":
        return y, (x, z)
    return z, (x, y)


def _dominant_axis(direction: tuple[float, float, float]) -> str:
    labels = ("x", "y", "z")
    values = [abs(direction[0]), abs(direction[1]), abs(direction[2])]
    return labels[values.index(max(values))]


def _pair(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    a = _num(value[0])
    b = _num(value[1])
    if a is None or b is None:
        return None
    return a, b


def _triple(value: Any) -> tuple[float, float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    a = _num(value[0])
    b = _num(value[1])
    c = _num(value[2])
    if a is None or b is None or c is None:
        return None
    return a, b, c


def _range(value: Any) -> list[float] | None:
    pair = _pair(value)
    if pair is None:
        return None
    return [pair[0], pair[1]]


def _range_midpoint(value: Any) -> float | None:
    pair = _pair(value)
    if pair is None:
        return None
    return (pair[0] + pair[1]) / 2.0


def _num(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _norm(value: Any) -> str:
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


def _find_param_hint(params: dict, keywords: frozenset | set) -> str | None:
    """Search params.json for keys matching keywords and return first numeric value.

    Iterates in dict insertion order (not sorted) to prefer keys that appear
    earlier in the user's params.json, which typically lists primary dimensions
    before derived ones like clearance.
    """
    if not isinstance(params, dict):
        return None
    for key, value in params.items():
        key_lower = str(key).lower()
        if any(kw in key_lower for kw in keywords) and isinstance(value, (int, float)):
            return str(value)
    return None
