from __future__ import annotations

from typing import Any

from ..contract.common import DIMENSION_CHECK_TYPES, HOLE_WORDS
from .facts import _hole_facts
from .geometry import (
    _best_center,
    _best_z,
    _bbox_shape,
    _bbox_expected_from_geometry,
    _bbox_expected_from_params,
    _clearance_min,
    _edge_guard_shape,
    _feature_region,
    _feature_z_range,
    _find_param_hint,
    _num,
    _pair,
    _tolerance,
)
from .types import SuggestContext


def _suggestion(feature: str, missing: str, reason: str, template: dict) -> dict[str, Any]:
    return {
        "feature": feature,
        "missing": missing,
        "reason": reason,
        "template": template,
    }


def _first_check_template(
    fid: str,
    categories: set[str],
    ctx: SuggestContext,
    *,
    feature: dict[str, Any],
    linked_checks: list[dict[str, Any]],
) -> dict:
    """Generate a starter check template based on feature classification."""
    if "hole" in categories:
        return _hole_accessibility_template(fid, ctx, feature=feature, linked_checks=linked_checks)
    if "load_bearing_attachment" in categories:
        return _attachment_root_template(fid, ctx, feature=feature, linked_checks=linked_checks)
    if "interface" in categories:
        return _interface_template(fid, ctx, feature=feature, linked_checks=linked_checks)
    return _bbox_template(fid, ctx)


def _geometry_template(
    fid: str,
    categories: set[str],
    ctx: SuggestContext,
    *,
    feature: dict[str, Any],
    linked_checks: list[dict[str, Any]],
) -> dict:
    """Template for a first geometry check when only non-geometry checks exist."""
    if "hole" in categories:
        hole = _hole_facts(fid, ctx, feature=feature, linked_checks=linked_checks)
        return {
            "id": f"{fid}_diameter",
            "type": "inner_diameter_at_z",
            "z": hole.get("position", _best_z(ctx)),
            "expected": hole.get("hole_diameter", _find_param_hint(ctx.params, HOLE_WORDS | {"diameter", "dia", "d"}) or "<diameter>"),
            "tolerance": _tolerance(ctx, default=0.3),
            "center": hole.get("center", _best_center(ctx)),
        }
    z = _best_z(ctx)
    region = _feature_region(ctx, feature)
    template: dict[str, Any] = {
        "id": f"{fid}_section",
        "type": "section_bbox_at_z",
        "z": z,
        "expected": "solid",
        "region": region,
    }
    if isinstance(_tolerance(ctx, default=None), (int, float)):
        template["tolerance"] = _tolerance(ctx, default=0.5)
    return template


def _bbox_template(fid: str, ctx: SuggestContext) -> dict:
    expected = _bbox_expected_from_params(ctx.params) or _bbox_expected_from_geometry(ctx.geometry)
    return {
        "id": f"{fid}_bbox",
        "type": "bbox_size",
        "expected": expected or ["<width>", "<depth>", "<height>"],
        "tolerance": _tolerance(ctx, default=0.5),
    }


def _hole_accessibility_template(
    fid: str,
    ctx: SuggestContext,
    *,
    feature: dict[str, Any],
    linked_checks: list[dict[str, Any]],
) -> dict:
    """Template for hole_accessibility check."""
    hole = _hole_facts(fid, ctx, feature=feature, linked_checks=linked_checks)
    axis = str(hole.get("axis", "z"))
    position = hole.get("position", _best_z(ctx))
    hole_diameter = hole.get("hole_diameter") or "<diameter>"
    clearance_diameter = hole.get("clearance_diameter")
    if clearance_diameter is None:
        numeric_hole = _num(hole_diameter)
        clearance_diameter = round(numeric_hole + 2.0, 4) if numeric_hole is not None else "<tool_diameter>"
    template: dict[str, Any] = {
        "id": f"{fid}_access",
        "type": "hole_accessibility",
        "axis": axis,
        "center": hole.get("center", _best_center(ctx)),
        "hole_diameter": hole_diameter,
        "clearance_diameter": clearance_diameter,
        "approach": "top",
    }
    template[axis if axis in ("x", "y", "z") else "position"] = position
    return template


def _attachment_root_template(
    fid: str,
    ctx: SuggestContext,
    *,
    feature: dict[str, Any],
    linked_checks: list[dict[str, Any]],
) -> dict:
    """Template for min_wall_thickness or min_clearance at attachment root."""
    wall_hint = _find_param_hint(ctx.params, {"wall", "thickness", "rib", "boss", "tab", "lip"})
    z_range = _feature_z_range(ctx, feature, linked_checks)
    if wall_hint:
        template: dict[str, Any] = {
            "id": f"{fid}_wall",
            "type": "min_wall_thickness",
            "region": _feature_region(ctx, feature),
            "min_mm": wall_hint,
        }
        if z_range:
            template.update({"axis": "z", "range": z_range, "samples": 5})
        else:
            template["z"] = _best_z(ctx)
        return template
    return _interface_template(fid, ctx, feature=feature, linked_checks=linked_checks, check_id=f"{fid}_clearance")


def _interface_template(
    fid: str,
    ctx: SuggestContext,
    *,
    feature: dict[str, Any],
    linked_checks: list[dict[str, Any]],
    check_id: str | None = None,
) -> dict:
    """Template for interface features: min_clearance between mating parts."""
    hole = _hole_facts(fid, ctx, feature=feature, linked_checks=linked_checks)
    edge_guard = _edge_guard_shape(ctx, hole.get("center")) if hole.get("center") else None
    if hole.get("shape") and edge_guard:
        return {
            "id": check_id or f"{fid}_clearance",
            "type": "min_clearance",
            "feature_a": hole["shape"],
            "feature_b": edge_guard,
            "min_mm": 0.0,
        }
    bbox = _bbox_shape(ctx)
    center = _pair(_best_center(ctx))
    if bbox and center:
        x0, x1 = [float(v) for v in bbox["x_range"]]
        y0, y1 = [float(v) for v in bbox["y_range"]]
        z0, z1 = [float(v) for v in bbox["z_range"]]
        cx, cy = center
        span = max(min(abs(x1 - x0), abs(y1 - y0)) * 0.1, 0.5)
        feature_box = {
            "type": "box",
            "role": "interface_probe",
            "x_range": [round(cx - span / 2.0, 4), round(cx + span / 2.0, 4)],
            "y_range": [round(cy - span / 2.0, 4), round(cy + span / 2.0, 4)],
            "z_range": [round(z0, 4), round(z1, 4)],
        }
        guard = _edge_guard_shape(ctx, [cx, cy]) or {
            "type": "box",
            "role": "bbox_reference",
            "x_range": [round(x0, 4), round(x1, 4)],
            "y_range": [round(y0, 4), round(y1, 4)],
            "z_range": [round(z0, 4), round(z1, 4)],
        }
        return {
            "id": check_id or f"{fid}_clearance",
            "type": "min_clearance",
            "feature_a": feature_box,
            "feature_b": guard,
            "min_mm": _clearance_min(ctx),
        }
    return {
        "id": check_id or f"{fid}_clearance",
        "type": "min_clearance",
        "feature_a": {"type": "<shape_type>", "<descriptor_fields>": "<values>"},
        "feature_b": {"type": "<shape_type>", "<descriptor_fields>": "<values>"},
        "min_mm": _clearance_min(ctx),
    }


def _append_evidence_suggestions(
    suggestions: list[dict[str, Any]],
    *,
    feature: dict[str, Any],
    categories: set[str],
    linked_types: set[str],
    linked_checks: list[dict[str, Any]],
    ctx: SuggestContext,
    existing_missing: set[str],
) -> None:
    fid = str(feature.get("id"))
    row = next((r for r in ctx.feature_evidence_matrix if r.get("feature") == fid), None)
    if not row:
        return
    for missing in row.get("missing") or []:
        if missing == "access" and "hole_accessibility" not in existing_missing:
            suggestions.append(_suggestion(
                fid,
                "hole_accessibility",
                "feature evidence matrix requires access evidence for this hole-like feature",
                _hole_accessibility_template(fid, ctx, feature=feature, linked_checks=linked_checks),
            ))
            existing_missing.add("hole_accessibility")
        elif missing == "wall" and "root_interface_check" not in existing_missing:
            suggestions.append(_suggestion(
                fid,
                "wall_thickness_check",
                "feature evidence matrix requires wall/root evidence for this structural feature",
                _attachment_root_template(fid, ctx, feature=feature, linked_checks=linked_checks),
            ))
            existing_missing.add("root_interface_check")
        elif missing == "interface_risk" and "interface_risk_check" not in existing_missing:
            suggestions.append(_suggestion(
                fid,
                "interface_risk_check",
                "feature evidence matrix requires edge-to-edge clearance or mating-interface evidence",
                _interface_template(fid, ctx, feature=feature, linked_checks=linked_checks),
            ))
            existing_missing.add("interface_risk_check")
        elif missing == "dimensions" and not (linked_types & DIMENSION_CHECK_TYPES):
            suggestions.append(_suggestion(
                fid,
                "dimension_check",
                "feature evidence matrix requires a size/dimension check, not only point presence",
                _geometry_template(fid, categories, ctx, feature=feature, linked_checks=linked_checks),
            ))
            existing_missing.add("dimension_check")
        elif missing == "position" and "position_check" not in existing_missing:
            suggestions.append(_suggestion(
                fid,
                "position_check",
                "feature evidence matrix requires explicit position evidence",
                _position_template(fid, ctx),
            ))
            existing_missing.add("position_check")


def _position_template(fid: str, ctx: SuggestContext) -> dict[str, Any]:
    center = _best_center(ctx)
    z = _best_z(ctx)
    return {
        "id": f"{fid}_position",
        "type": "feature_position",
        "point": [center[0], center[1], z],
        "expected": "solid",
        "tolerance_mm": _tolerance(ctx, default=0.5),
    }
