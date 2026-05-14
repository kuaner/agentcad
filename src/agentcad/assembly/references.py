from __future__ import annotations

from typing import Any

from ..geometry import parse_shape
from ..stl import Vec3, dot, normalize, sub
from .transform import _round_vec, _transform_point, _transform_point_matrix, _transform_vector, _vec3
from .types import AssemblyError, Transform


def _collect_references(contract: dict) -> list[str]:
    refs: list[str] = []
    for mate in contract.get("mates", []) or []:
        if isinstance(mate, dict):
            for key in ("a", "b"):
                _append_ref(refs, mate.get(key))
    for check in contract.get("checks", []) or []:
        if isinstance(check, dict):
            for key in ("ref", "path", "a", "b", "inner", "outer", "feature_a", "feature_b", "shape_a", "shape_b"):
                _append_ref_value(refs, check.get(key))
    for interface in contract.get("interfaces", []) or []:
        if isinstance(interface, dict):
            for key in ("a", "b", "feature_a", "feature_b", "inner", "outer"):
                _append_ref_value(refs, interface.get(key))
    return sorted(set(refs))


def _append_ref(refs: list[str], value: Any) -> None:
    if isinstance(value, str) and "." in value:
        refs.append(value)


def _append_ref_value(refs: list[str], value: Any) -> None:
    _append_ref(refs, value)
    if isinstance(value, dict) and isinstance(value.get("ref"), str):
        _append_ref(refs, value.get("ref"))


def _resolve_references(refs: list[str], components: dict[str, dict]) -> dict[str, dict]:
    resolved: dict[str, dict] = {}
    for ref in refs:
        parts = ref.split(".")
        cid = parts[0]
        record = components.get(cid)
        if record is None:
            resolved[ref] = {
                "ok": False,
                "ref": ref,
                "component": cid,
                "error": {"type": "ComponentMissing", "message": f"unknown component: {cid}"},
            }
            continue
        local = _dig(record.get("metadata") or {}, parts[1:])
        if local is None:
            resolved[ref] = {
                "ok": False,
                "ref": ref,
                "component": cid,
                "path": ".".join(parts[1:]),
                "error": {"type": "ReferenceMissing", "message": f"metadata reference not found: {ref}"},
            }
            continue
        resolved[ref] = {
            "ok": True,
            "ref": ref,
            "component": cid,
            "path": ".".join(parts[1:]),
            "local": local,
            "world": _transform_descriptor(local, record["transform"]),
        }
    return resolved


def _dig(value: Any, parts: list[str]) -> Any:
    current = value
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _transform_descriptor(value: Any, transform: Transform) -> Any:
    if isinstance(value, list):
        return [_transform_descriptor(item, transform) for item in value]
    if not isinstance(value, dict):
        return value
    if _is_axis_descriptor(value):
        point = _vec3(value.get("point", [0, 0, 0]), "axis.point")
        direction = _vec3(value.get("direction", [0, 0, 1]), "axis.direction")
        return {
            **value,
            "point": list(value.get("point", [0, 0, 0])),
            "direction": list(value.get("direction", [0, 0, 1])),
            "world_point": _round_vec(_transform_point(point, transform)),
            "world_direction": _round_vec(_transform_vector(direction, transform)),
        }
    if _is_cylinder_descriptor(value):
        endpoints = _cylinder_endpoints(value)
        world_a = _transform_point(endpoints[0], transform)
        world_b = _transform_point(endpoints[1], transform)
        return {
            **value,
            "world_axis_point": _round_vec(world_a),
            "world_axis_end": _round_vec(world_b),
            "world_axis_direction": _round_vec(normalize(sub(world_b, world_a))),
            "radius_mm": _descriptor_radius(value),
        }
    if _is_box_descriptor(value):
        return {
            **value,
            "world_shape": _transform_shape_descriptor(value, transform.matrix),
        }
    if _is_sphere_descriptor(value):
        return {
            **value,
            "world_shape": _transform_shape_descriptor(value, transform.matrix),
        }
    transformed = {}
    for key, item in value.items():
        transformed[key] = _transform_descriptor(item, transform)
    return transformed


def _is_axis_descriptor(value: Any) -> bool:
    return isinstance(value, dict) and "point" in value and "direction" in value


def _is_cylinder_descriptor(value: Any) -> bool:
    return isinstance(value, dict) and value.get("type") == "cylinder"


def _is_box_descriptor(value: Any) -> bool:
    return isinstance(value, dict) and value.get("type") == "box"


def _is_sphere_descriptor(value: Any) -> bool:
    return isinstance(value, dict) and value.get("type") == "sphere"


def _descriptor_radius(desc: dict) -> float | None:
    for key in ("radius_mm", "radius"):
        if key in desc:
            return float(desc[key])
    if "diameter_mm" in desc:
        return float(desc["diameter_mm"]) / 2.0
    if "diameter" in desc:
        return float(desc["diameter"]) / 2.0
    return None


def _descriptor_float(value: Any, label: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise AssemblyError("CylinderDescriptorInvalid", f"{label} must be numeric") from exc


def _descriptor_center(desc: dict, axis: str) -> tuple[float, ...]:
    center = desc.get("center", [0.0, 0.0])
    if not isinstance(center, (list, tuple)):
        raise AssemblyError("CylinderDescriptorInvalid", "cylinder center must be a number array")
    if axis == "z":
        if len(center) not in (2, 3):
            raise AssemblyError("CylinderDescriptorInvalid", "z-axis cylinder center must contain two or three values")
        return (_descriptor_float(center[0], "cylinder center[0]"), _descriptor_float(center[1], "cylinder center[1]"))
    if axis in ("x", "y"):
        if len(center) < 2:
            raise AssemblyError("CylinderDescriptorInvalid", f"{axis}-axis cylinder center must contain at least two values")
        return (_descriptor_float(center[0], "cylinder center[0]"), _descriptor_float(center[1], "cylinder center[1]"))
    raise AssemblyError("CylinderDescriptorInvalid", f"unsupported cylinder axis: {axis}")


def _cylinder_endpoints(desc: dict) -> tuple[Vec3, Vec3]:
    axis = str(desc.get("axis", "z")).lower()
    range_key = f"{axis}_range"
    axis_range = desc.get(range_key) or desc.get("range") or [0.0, 0.0]
    if not isinstance(axis_range, (list, tuple)) or len(axis_range) != 2:
        raise AssemblyError("CylinderDescriptorInvalid", f"cylinder {range_key} must contain two values")
    start = _descriptor_float(axis_range[0], f"cylinder {range_key}[0]")
    end = _descriptor_float(axis_range[1], f"cylinder {range_key}[1]")
    center = _descriptor_center(desc, str(axis))
    if axis == "z":
        return ((center[0], center[1], start), (center[0], center[1], end))
    if axis == "x":
        y, z = center[0], center[1]
        return ((start, y, z), (end, y, z))
    if axis == "y":
        x, z = center[0], center[1]
        return ((x, start, z), (x, end, z))
    raise AssemblyError("CylinderDescriptorInvalid", f"unsupported cylinder axis: {axis}")


def _transform_shape_descriptor(desc: Any, matrix: list[list[float]]) -> dict:
    if not isinstance(desc, dict):
        raise AssemblyError("ShapeDescriptorInvalid", "shape descriptor must be an object")
    normalized = _normalize_shape_descriptor(desc)
    kind = normalized.get("type")
    if kind == "sphere":
        center = _vec3(normalized["center"], "sphere.center")
        return parse_shape({"type": "sphere", "center": _round_vec(_transform_point_matrix(center, matrix)), "radius": float(normalized["radius"])})
    if kind == "box":
        corners = _box_corners(normalized)
        world = [_transform_point_matrix(point, matrix) for point in corners]
        return parse_shape(
            {
                "type": "box",
                "x_range": [min(point[0] for point in world), max(point[0] for point in world)],
                "y_range": [min(point[1] for point in world), max(point[1] for point in world)],
                "z_range": [min(point[2] for point in world), max(point[2] for point in world)],
            }
        )
    if kind == "cylinder":
        radius = float(normalized["radius"])
        a, b = _cylinder_endpoints(normalized)
        world_a = _transform_point_matrix(a, matrix)
        world_b = _transform_point_matrix(b, matrix)
        axis_name = _cardinal_axis_name(normalize(sub(world_b, world_a)))
        if axis_name is None:
            # The static relation solver is axis-aligned. For rotated cylinders,
            # fall back to a conservative world AABB expanded by radius.
            min_v = [min(world_a[i], world_b[i]) - radius for i in range(3)]
            max_v = [max(world_a[i], world_b[i]) + radius for i in range(3)]
            return parse_shape({"type": "box", "x_range": [min_v[0], max_v[0]], "y_range": [min_v[1], max_v[1]], "z_range": [min_v[2], max_v[2]]})
        if axis_name == "z":
            return parse_shape(
                {
                    "type": "cylinder",
                    "axis": "z",
                    "center": [(world_a[0] + world_b[0]) / 2.0, (world_a[1] + world_b[1]) / 2.0],
                    "radius": radius,
                    "z_range": sorted([world_a[2], world_b[2]]),
                }
            )
        if axis_name == "x":
            return parse_shape(
                {
                    "type": "cylinder",
                    "axis": "x",
                    "center": [(world_a[1] + world_b[1]) / 2.0, (world_a[2] + world_b[2]) / 2.0],
                    "radius": radius,
                    "x_range": sorted([world_a[0], world_b[0]]),
                }
            )
        return parse_shape(
            {
                "type": "cylinder",
                "axis": "y",
                "center": [(world_a[0] + world_b[0]) / 2.0, (world_a[2] + world_b[2]) / 2.0],
                "radius": radius,
                "y_range": sorted([world_a[1], world_b[1]]),
            }
        )
    raise AssemblyError("ShapeDescriptorInvalid", f"unsupported shape descriptor: {kind}")


def _normalize_shape_descriptor(desc: dict) -> dict:
    result = dict(desc)
    if result.get("type") == "cylinder":
        radius = _descriptor_radius(result)
        if radius is None:
            raise AssemblyError("ShapeDescriptorInvalid", "cylinder shape must include radius/radius_mm or diameter/diameter_mm")
        result["radius"] = radius
        axis = str(result.get("axis", "z")).lower()
        if axis == "x" and "x_range" not in result and "range" in result:
            result["x_range"] = result["range"]
        if axis == "y" and "y_range" not in result and "range" in result:
            result["y_range"] = result["range"]
        if axis == "z" and "z_range" not in result and "range" in result:
            result["z_range"] = result["range"]
    if result.get("type") == "sphere" and "radius" not in result and "radius_mm" in result:
        result["radius"] = result["radius_mm"]
    return result


def _box_corners(shape: dict) -> list[Vec3]:
    x0, x1 = sorted([float(shape["x_range"][0]), float(shape["x_range"][1])])
    y0, y1 = sorted([float(shape["y_range"][0]), float(shape["y_range"][1])])
    z0, z1 = sorted([float(shape["z_range"][0]), float(shape["z_range"][1])])
    return [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]


def _cardinal_axis_name(direction: Vec3, tol: float = 1e-6) -> str | None:
    axes = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}
    for name, axis in axes.items():
        if abs(abs(dot(direction, axis)) - 1.0) <= tol:
            return name
    return None


def _components_from_refs(refs: list[Any]) -> list[str]:
    components = []
    for ref in refs:
        if isinstance(ref, str) and "." in ref:
            components.append(ref.split(".", 1)[0])
        elif isinstance(ref, dict) and isinstance(ref.get("ref"), str) and "." in ref["ref"]:
            components.append(ref["ref"].split(".", 1)[0])
        elif isinstance(ref, dict) and ref.get("component"):
            components.append(str(ref["component"]))
    return sorted(set(components))
