from __future__ import annotations

from typing import Any

from ..contract.common import HOLE_WORDS
from .geometry import (
    _axis_position_and_center,
    _best_center,
    _best_z,
    _dominant_axis,
    _feature_axis_range,
    _find_param_hint,
    _norm,
    _num,
    _pair,
    _range_midpoint,
    _triple,
)
from .types import SuggestContext

def _hole_facts(
    fid: str,
    ctx: SuggestContext,
    *,
    feature: dict[str, Any],
    linked_checks: list[dict[str, Any]],
) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    for check in linked_checks:
        check_type = str(check.get("type", ""))
        if check_type == "inner_diameter_at_z":
            if check.get("expected") is not None:
                facts["hole_diameter"] = str(check["expected"])
            if check.get("z") is not None:
                facts["axis"] = "z"
                facts["position"] = check["z"]
            center = _pair(check.get("center"))
            if center:
                facts["center"] = [center[0], center[1]]
            break
        if check_type == "hole_accessibility":
            axis = str(check.get("axis", "z")).lower()
            facts["axis"] = axis
            pos = check.get(axis, check.get("position", check.get("z")))
            if pos is not None:
                facts["position"] = pos
            center = _pair(check.get("center"))
            if center:
                facts["center"] = [center[0], center[1]]

    facts.update({k: v for k, v in _metadata_hole_facts(fid, ctx.metadata).items() if k not in facts})

    if "hole_diameter" not in facts:
        diameter_hint = _find_param_hint(ctx.params, HOLE_WORDS | {"diameter", "dia", "d", "radius", "r"})
        if diameter_hint:
            facts["hole_diameter"] = diameter_hint
    if "clearance_diameter" not in facts:
        clearance_hint = _find_param_hint(ctx.params, {"clearance", "tool", "fastener", "screw", "bolt", "driver"})
        if clearance_hint:
            facts["clearance_diameter"] = clearance_hint
    if "axis" not in facts:
        facts["axis"] = "z"
    if "position" not in facts:
        facts["position"] = _best_z(ctx)
    if "center" not in facts:
        facts["center"] = _best_center(ctx)

    shape = _hole_shape_from_facts(ctx, feature, linked_checks, facts)
    if shape:
        facts["shape"] = shape
    return facts


def _metadata_hole_facts(fid: str, metadata: dict[str, Any]) -> dict[str, Any]:
    interfaces = metadata.get("interfaces") if isinstance(metadata, dict) else {}
    if not isinstance(interfaces, dict):
        return {}
    fid_norm = _norm(fid)
    candidates = [
        iface for name, iface in interfaces.items()
        if isinstance(iface, dict) and (fid_norm in _norm(name) or _norm(name) in fid_norm)
    ]
    if not candidates and len(interfaces) == 1:
        only = next(iter(interfaces.values()))
        if isinstance(only, dict):
            candidates = [only]
    if not candidates:
        return {}

    iface = candidates[0]
    facts: dict[str, Any] = {}
    axis = iface.get("axis")
    if isinstance(axis, dict):
        point = _triple(axis.get("point"))
        direction = _triple(axis.get("direction"))
        if point and direction:
            axis_name = _dominant_axis(direction)
            position, center = _axis_position_and_center(axis_name, point)
            facts.update({"axis": axis_name, "position": position, "center": [center[0], center[1]]})
    if iface.get("clearance_diameter") is not None:
        facts["clearance_diameter"] = str(iface["clearance_diameter"])

    for key in ("inner_cylinder", "outer_cylinder"):
        desc = iface.get(key)
        if not isinstance(desc, dict) or desc.get("type") != "cylinder":
            continue
        axis_name = str(desc.get("axis", "z")).lower()
        center = _pair(desc.get("center"))
        if center:
            facts.setdefault("axis", axis_name)
            facts.setdefault("center", [center[0], center[1]])
        rng = desc.get(f"{axis_name}_range")
        midpoint = _range_midpoint(rng)
        if midpoint is not None:
            facts.setdefault("position", midpoint)
        if desc.get("radius") is not None and key == "inner_cylinder":
            try:
                facts.setdefault("hole_diameter", str(float(desc["radius"]) * 2.0))
            except (TypeError, ValueError):
                pass
    return facts


def _hole_shape_from_facts(
    ctx: SuggestContext,
    feature: dict[str, Any],
    linked_checks: list[dict[str, Any]],
    facts: dict[str, Any],
) -> dict[str, Any] | None:
    axis = str(facts.get("axis", "z")).lower()
    center = _pair(facts.get("center"))
    diameter = _num(facts.get("hole_diameter"))
    if axis not in ("x", "y", "z") or center is None or diameter is None:
        return None
    rng = _feature_axis_range(ctx, feature, linked_checks, axis, fallback_position=_num(facts.get("position")))
    if not rng:
        return None
    return {
        "type": "cylinder",
        "axis": axis,
        "center": [center[0], center[1]],
        "radius": round(diameter / 2.0, 4),
        f"{axis}_range": rng,
    }
