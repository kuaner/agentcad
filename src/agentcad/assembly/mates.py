from __future__ import annotations

import math
from typing import Any

from ..stl import Vec3, cross, dot, length, normalize, sub
from .references import _components_from_refs
from .transform import _vec3
from .types import AssemblyError


def _evaluate_mates(contract: dict, resolved_refs: dict[str, dict]) -> list[dict]:
    results = []
    for index, mate in enumerate(contract.get("mates", []) or []):
        if not isinstance(mate, dict):
            continue
        mtype = mate.get("type")
        name = mate.get("id") or f"mate_{index}"
        if mtype in ("coaxial", "mate_coaxial"):
            results.append(_eval_mate_coaxial(name, mate, resolved_refs))
        elif mtype in ("axis_aligned", "mate_axis_aligned"):
            results.append(_eval_mate_axis_aligned(name, mate, resolved_refs))
        elif mtype in ("coincident", "mate_coincident"):
            results.append(_eval_mate_coincident(name, mate, resolved_refs))
        elif mtype == "axial_engagement":
            results.append(_eval_axial_engagement(name, mate, resolved_refs))
        else:
            results.append(
                {
                    "name": name,
                    "type": mtype,
                    "ok": False,
                    "measurable": False,
                    "error": {"type": "UnsupportedMateType", "message": f"unsupported mate type: {mtype}"},
                }
            )
    return results


def _eval_mate_coaxial(name: str, mate: dict, refs: dict[str, dict]) -> dict:
    max_angle = _required_float(mate, "max_axis_angle_deg", name)
    max_offset = _required_float(mate, "max_radial_offset_mm", name)
    axis_a = _axis_from_ref(mate.get("a"), refs)
    axis_b = _axis_from_ref(mate.get("b"), refs)
    if axis_a is None or axis_b is None:
        return _unmeasurable_mate(name, "coaxial", mate, "AxisMissing", "both refs must resolve to axis-like descriptors")
    angle = _angle_deg(axis_a[1], axis_b[1])
    radial_offset = _point_axis_distance(axis_b[0], axis_a[0], axis_a[1])
    ok = max_angle is not None and max_offset is not None and angle <= max_angle and radial_offset <= max_offset
    return {
        "name": name,
        "type": "mate_coaxial",
        "ok": ok,
        "measurable": True,
        "components": _components_from_refs([mate.get("a"), mate.get("b")]),
        "angle_deg": angle,
        "radial_offset_mm": radial_offset,
        "max_axis_angle_deg": max_angle,
        "max_radial_offset_mm": max_offset,
    }


def _eval_mate_axis_aligned(name: str, mate: dict, refs: dict[str, dict]) -> dict:
    max_angle = _required_float(mate, "max_axis_angle_deg", name)
    axis_a = _axis_from_ref(mate.get("a"), refs)
    axis_b = _axis_from_ref(mate.get("b"), refs)
    if axis_a is None or axis_b is None:
        return _unmeasurable_mate(name, "axis_aligned", mate, "AxisMissing", "both refs must resolve to axis-like descriptors")
    angle = _angle_deg(axis_a[1], axis_b[1])
    return {
        "name": name,
        "type": "mate_axis_aligned",
        "ok": max_angle is not None and angle <= max_angle,
        "measurable": True,
        "components": _components_from_refs([mate.get("a"), mate.get("b")]),
        "angle_deg": angle,
        "max_axis_angle_deg": max_angle,
    }


def _eval_mate_coincident(name: str, mate: dict, refs: dict[str, dict]) -> dict:
    max_distance = _required_float(mate, "max_distance_mm", name)
    point_a = _point_from_ref(mate.get("a"), refs)
    point_b = _point_from_ref(mate.get("b"), refs)
    if point_a is None or point_b is None:
        return _unmeasurable_mate(name, "coincident", mate, "PointMissing", "both refs must resolve to point-like descriptors")
    distance = length(sub(point_b, point_a))
    return {
        "name": name,
        "type": "mate_coincident",
        "ok": max_distance is not None and distance <= max_distance,
        "measurable": True,
        "components": _components_from_refs([mate.get("a"), mate.get("b")]),
        "distance_mm": distance,
        "max_distance_mm": max_distance,
    }


def _eval_axial_engagement(name: str, mate: dict, refs: dict[str, dict]) -> dict:
    min_mm = _required_float(mate, "min_mm", name)
    interval_a = _axis_interval_from_ref(mate.get("a"), refs)
    interval_b = _axis_interval_from_ref(mate.get("b"), refs)
    if interval_a is None or interval_b is None:
        return _unmeasurable_mate(name, "axial_engagement", mate, "AxisIntervalMissing", "both refs must resolve to cylindrical or axis interval descriptors")
    axis = interval_a["axis"]
    projections_a = [dot(point, axis) for point in interval_a["points"]]
    projections_b = [dot(point, axis) for point in interval_b["points"]]
    a_min, a_max = min(projections_a), max(projections_a)
    b_min, b_max = min(projections_b), max(projections_b)
    overlap = max(0.0, min(a_max, b_max) - max(a_min, b_min))
    return {
        "name": name,
        "type": "axial_engagement",
        "ok": min_mm is not None and overlap >= min_mm,
        "measurable": True,
        "components": _components_from_refs([mate.get("a"), mate.get("b")]),
        "actual_mm": overlap,
        "min_mm": min_mm,
        "intervals": {
            "a": [a_min, a_max],
            "b": [b_min, b_max],
        },
    }


def _required_float(payload: dict, key: str, name: str) -> float | None:
    if key not in payload:
        raise AssemblyError("RequiredFieldMissing", f"{name}.{key} is required")
    try:
        return float(payload[key])
    except (TypeError, ValueError) as exc:
        raise AssemblyError("ToleranceInvalid", f"{name}.{key} must be numeric") from exc


def _unmeasurable_mate(name: str, mtype: str, mate: dict, error_type: str, message: str) -> dict:
    return {
        "name": name,
        "type": f"mate_{mtype}",
        "ok": False,
        "measurable": False,
        "components": _components_from_refs([mate.get("a"), mate.get("b")]),
        "error": {"type": error_type, "message": message},
    }


def _axis_from_ref(ref: Any, refs: dict[str, dict]) -> tuple[Vec3, Vec3] | None:
    if not isinstance(ref, str):
        return None
    resolved = refs.get(ref)
    if not resolved or not resolved.get("ok"):
        return None
    return _axis_from_descriptor(resolved.get("world"))


def _axis_from_descriptor(desc: Any) -> tuple[Vec3, Vec3] | None:
    if not isinstance(desc, dict):
        return None
    if "world_point" in desc and "world_direction" in desc:
        return (_vec3(desc["world_point"], "axis.world_point"), normalize(_vec3(desc["world_direction"], "axis.world_direction")))
    if "world_axis_point" in desc and "world_axis_direction" in desc:
        return (
            _vec3(desc["world_axis_point"], "cylinder.world_axis_point"),
            normalize(_vec3(desc["world_axis_direction"], "cylinder.world_axis_direction")),
        )
    if "axis" in desc:
        return _axis_from_descriptor(desc["axis"])
    for key in ("outer_cylinder", "inner_cylinder", "cylinder"):
        if key in desc:
            axis = _axis_from_descriptor(desc[key])
            if axis is not None:
                return axis
    return None


def _point_from_ref(ref: Any, refs: dict[str, dict]) -> Vec3 | None:
    if not isinstance(ref, str):
        return None
    resolved = refs.get(ref)
    if not resolved or not resolved.get("ok"):
        return None
    return _point_from_descriptor(resolved.get("world"))


def _point_from_descriptor(desc: Any) -> Vec3 | None:
    if not isinstance(desc, dict):
        return None
    if "world_point" in desc:
        return _vec3(desc["world_point"], "point.world_point")
    if "world_axis_point" in desc:
        return _vec3(desc["world_axis_point"], "cylinder.world_axis_point")
    if "axis" in desc:
        point = _point_from_descriptor(desc["axis"])
        if point is not None:
            return point
    for key in ("outer_cylinder", "inner_cylinder", "cylinder"):
        if key in desc:
            point = _point_from_descriptor(desc[key])
            if point is not None:
                return point
    return None


def _axis_interval_from_ref(ref: Any, refs: dict[str, dict]) -> dict | None:
    if not isinstance(ref, str):
        return None
    resolved = refs.get(ref)
    if not resolved or not resolved.get("ok"):
        return None
    return _axis_interval_from_descriptor(resolved.get("world"))


def _axis_interval_from_descriptor(desc: Any) -> dict | None:
    if not isinstance(desc, dict):
        return None
    if "world_axis_point" in desc and "world_axis_end" in desc:
        a = _vec3(desc["world_axis_point"], "cylinder.world_axis_point")
        b = _vec3(desc["world_axis_end"], "cylinder.world_axis_end")
        return {"axis": normalize(sub(b, a)), "points": [a, b]}
    for key in ("outer_cylinder", "inner_cylinder", "cylinder"):
        if key in desc:
            interval = _axis_interval_from_descriptor(desc[key])
            if interval is not None:
                return interval
    return None


def _angle_deg(a: Vec3, b: Vec3) -> float:
    value = max(-1.0, min(1.0, abs(dot(normalize(a), normalize(b)))))
    return math.degrees(math.acos(value))


def _point_axis_distance(point: Vec3, axis_point: Vec3, axis_dir: Vec3) -> float:
    return length(cross(sub(point, axis_point), normalize(axis_dir)))
