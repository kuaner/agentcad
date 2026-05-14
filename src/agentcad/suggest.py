"""Suggest-checks command: recommend missing checks based on design.json.

``agentcad suggest-checks <model>`` reads the design contract and produces
conservative check templates for features that lack essential checks.

Output schema:
  {
    "ok": bool,
    "stage": "suggest-checks",
    "model": str,
    "suggestions": [{feature, missing, reason, template}],
    "design_found": bool
  }
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contract import (
    ROOT_CHECK_TYPES,
    HOLE_CHECK_TYPES,
    HOLE_WORDS,
    DIMENSION_CHECK_TYPES,
    GEOMETRY_CHECK_TYPES,
    classify_feature,
    evaluate_design_intent_lint_dict,
    evaluate_feature_evidence_matrix_dict,
)
from .jsonio import read_json
from .probe.planner import plan_probe_points
from .workspace import model_dir, outputs_dir


@dataclass(frozen=True)
class SuggestContext:
    params: dict[str, Any]
    metadata: dict[str, Any]
    geometry: dict[str, Any]
    validation: dict[str, Any]
    observability: dict[str, Any]
    feature_evidence_matrix: list[dict[str, Any]]
    probe_plan: list[dict[str, Any]]


def suggest_checks(project: Path, name: str) -> dict[str, Any]:
    """Analyze design.json and suggest missing checks."""
    mdir = model_dir(project, name)
    design = read_json(mdir / "design.json", default=None)

    if design is None or not isinstance(design, dict):
        return {
            "ok": False,
            "stage": "suggest-checks",
            "model": name,
            "suggestions": [],
            "design_found": False,
            "error": {"type": "DesignNotFound", "message": f"design.json not found for model '{name}'"},
        }

    features = design.get("features") or []
    checks = design.get("checks") or []
    params = read_json(mdir / "params.json", default={})
    metadata = read_json(mdir / "metadata.json", default={}) or {}
    out_dir = outputs_dir(project, name)
    geometry = read_json(out_dir / "geometry.json", default={}) or {}
    validation = read_json(out_dir / "validation.json", default={}) or {}
    observability = read_json(out_dir / "observability.json", default={}) or {}
    feature_evidence_matrix = evaluate_feature_evidence_matrix_dict(design)
    design_intent_lint = evaluate_design_intent_lint_dict(design)
    probe_plan = plan_probe_points(
        name,
        design,
        params=params if isinstance(params, dict) else {},
        metadata=metadata if isinstance(metadata, dict) else {},
        geometry=geometry if isinstance(geometry, dict) else {},
        validation=validation if isinstance(validation, dict) else {},
        observability=observability if isinstance(observability, dict) else {},
        feature_evidence_matrix=feature_evidence_matrix,
    )
    ctx = SuggestContext(
        params=params if isinstance(params, dict) else {},
        metadata=metadata if isinstance(metadata, dict) else {},
        geometry=geometry if isinstance(geometry, dict) else {},
        validation=validation if isinstance(validation, dict) else {},
        observability=observability if isinstance(observability, dict) else {},
        feature_evidence_matrix=feature_evidence_matrix,
        probe_plan=probe_plan,
    )

    # Build a map: check_id -> check_type
    check_type_map: dict[str, str] = {}
    check_map: dict[str, dict[str, Any]] = {}
    for c in checks:
        if isinstance(c, dict) and c.get("id") and c.get("type"):
            check_type_map[str(c["id"])] = str(c["type"])
            check_map[str(c["id"])] = c

    # Build a map: feature_id -> set of linked check types
    feature_check_types: dict[str, set[str]] = {}
    for feature in features:
        if not isinstance(feature, dict) or not feature.get("id"):
            continue
        fid = str(feature["id"])
        linked_ids = [str(cid) for cid in (feature.get("checks") or [])]
        feature_check_types[fid] = {check_type_map.get(cid, "") for cid in linked_ids if cid in check_type_map}

    suggestions: list[dict[str, Any]] = []

    for feature in features:
        if not isinstance(feature, dict) or not feature.get("id"):
            continue
        fid = str(feature["id"])
        categories = classify_feature(feature)
        linked_types = feature_check_types.get(fid, set())
        linked_checks = [
            check_map[cid] for cid in (str(cid) for cid in (feature.get("checks") or []))
            if cid in check_map
        ]
        feature_suggestion_missing: set[str] = set()

        # No checks at all.
        if not linked_types:
            suggestions.append(_suggestion(
                fid, "any_check",
                f"feature '{fid}' has no linked checks — add at least one geometry check",
                _first_check_template(fid, categories, ctx, feature=feature, linked_checks=linked_checks),
            ))
            feature_suggestion_missing.add("any_check")
            continue

        # No geometry checks.
        geom = linked_types & GEOMETRY_CHECK_TYPES
        if not geom:
            suggestions.append(_suggestion(
                fid, "geometry_check",
                f"feature '{fid}' has only non-geometry checks — add a section, diameter, or clearance check",
                _geometry_template(fid, categories, ctx, feature=feature, linked_checks=linked_checks),
            ))
            feature_suggestion_missing.add("geometry_check")
            continue

        # Hole-specific: missing hole_accessibility.
        if "hole" in categories:
            hole_checks = linked_types & HOLE_CHECK_TYPES
            if "hole_accessibility" not in hole_checks and "hole_accessibility" not in linked_types:
                suggestions.append(_suggestion(
                    fid, "hole_accessibility",
                    "hole-like feature has diameter/clearance checks but no tool envelope check",
                    _hole_accessibility_template(fid, ctx, feature=feature, linked_checks=linked_checks),
                ))
                feature_suggestion_missing.add("hole_accessibility")

        # Load-bearing attachment: missing root/interface check.
        if "load_bearing_attachment" in categories:
            root_checks = linked_types & ROOT_CHECK_TYPES
            if not root_checks:
                suggestions.append(_suggestion(
                    fid, "root_interface_check",
                    "load-bearing feature has no root/interface check — detachment risk is unverified",
                    _attachment_root_template(fid, ctx, feature=feature, linked_checks=linked_checks),
                ))
                feature_suggestion_missing.add("root_interface_check")

        _append_evidence_suggestions(
            suggestions,
            feature=feature,
            categories=categories,
            linked_types=linked_types,
            linked_checks=linked_checks,
            ctx=ctx,
            existing_missing=feature_suggestion_missing,
        )

    return {
        "ok": True,
        "stage": "suggest-checks",
        "model": name,
        "suggestions": suggestions,
        "feature_evidence_matrix": feature_evidence_matrix,
        "design_intent_lint": design_intent_lint,
        "probe_plan": probe_plan,
        "design_found": True,
    }


def _suggestion(feature: str, missing: str, reason: str, template: dict) -> dict[str, Any]:
    return {
        "feature": feature,
        "missing": missing,
        "reason": reason,
        "template": template,
    }


# ── Template generators ────────────────────────────────────────────────────


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
    template: dict[str, Any] = {
        "id": f"{fid}_access",
        "type": "hole_accessibility",
        "axis": axis,
        "center": hole.get("center", _best_center(ctx)),
        "hole_diameter": hole.get("hole_diameter") or "<diameter>",
        "clearance_diameter": hole.get("clearance_diameter") or "<tool_diameter>",
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
