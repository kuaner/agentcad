from __future__ import annotations

from typing import Any

from ..contract.common import classify_feature
from ..contract.evidence import evaluate_feature_evidence_matrix_dict
from ..geometry import shape_aabb
from .utils import _fmt, _mid_pair, _norm, _num, _pair, _region, _region_arg, _triple


def plan_probe_points(
    name: str,
    design: dict[str, Any],
    *,
    params: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    geometry: dict[str, Any] | None = None,
    validation: dict[str, Any] | None = None,
    observability: dict[str, Any] | None = None,
    feature_evidence_matrix: list[dict] | None = None,
) -> list[dict]:
    """Pure planner used by `probe --plan` and `suggest-checks`.

    It plans from declared intent first, then enriches with measured bbox/scan
    positions when those artifacts already exist.
    """
    params = params if isinstance(params, dict) else {}
    metadata = metadata if isinstance(metadata, dict) else {}
    geometry = geometry if isinstance(geometry, dict) else {}
    validation = validation if isinstance(validation, dict) else {}
    observability = observability if isinstance(observability, dict) else {}
    matrix = feature_evidence_matrix or evaluate_feature_evidence_matrix_dict(design)
    matrix_by_feature = {row.get("feature"): row for row in matrix}
    failures_by_feature = _failure_modes_by_feature(design)

    checks = [
        c for c in (design.get("checks") or [])
        if isinstance(c, dict) and c.get("id")
    ]
    check_map = {str(c["id"]): c for c in checks}
    suggestions: list[dict] = []

    for feature in design.get("features") or []:
        if not isinstance(feature, dict) or not feature.get("id"):
            continue
        fid = str(feature["id"])
        categories = classify_feature(feature)
        linked = [
            check_map[str(cid)]
            for cid in (feature.get("checks") or [])
            if str(cid) in check_map
        ]
        for failure in failures_by_feature.get(fid, []):
            suggestion = _probe_for_failure_mode(
                name,
                fid,
                failure,
                params=params,
                metadata=metadata,
                geometry=geometry,
                validation=validation,
                linked_checks=linked,
            )
            if suggestion:
                suggestions.append(suggestion)
        for check in linked:
            suggestion = _probe_for_check(name, fid, check)
            if suggestion:
                suggestions.append(suggestion)
        row = matrix_by_feature.get(fid) or {}
        for missing in row.get("missing") or []:
            suggestions.append(_probe_for_missing_evidence(
                name,
                fid,
                missing,
                categories,
                params=params,
                metadata=metadata,
                geometry=geometry,
                validation=validation,
                failure_modes=failures_by_feature.get(fid, []),
            ))

    for step in _interesting_step_changes(geometry, validation, observability)[:3]:
        pos = _num(step.get("pos"))
        if pos is None:
            continue
        suggestions.append({
            "id": f"scan_transition_z{_fmt(pos)}",
            "priority": 70,
            "source": "probe_scan",
            "purpose": step.get("hint") or "inspect detected section transition",
            "command": f"agentcad probe {name} --z {_fmt(pos)}",
            "render_command": f"agentcad render {name} --section-z {_fmt(pos)}",
            "probe": {"axis": "z", "position": pos},
        })

    if not suggestions:
        suggestions.append({
            "id": "scan_z",
            "priority": 10,
            "source": "fallback",
            "purpose": "discover section transitions before choosing checks",
            "command": f"agentcad probe {name} --scan --axis z",
            "probe": {"axis": "z", "samples": 20},
        })

    return _dedupe_probe_suggestions(suggestions)


def _probe_for_check(name: str, fid: str, check: dict[str, Any]) -> dict | None:
    check_id = str(check.get("id") or "")
    check_type = str(check.get("type") or "")

    if check_type in ("inner_diameter_at_z", "outer_diameter_at_z"):
        z = _num(check.get("z"))
        center = _pair(check.get("center")) or (0.0, 0.0)
        if z is None:
            return None
        return {
            "id": f"{check_id}_probe",
            "priority": 100,
            "source": "check",
            "feature": fid,
            "check": check_id,
            "check_type": check_type,
            "purpose": "measure diameter and verify the declared center on the section plane",
            "command": f"agentcad probe {name} --z {_fmt(z)} --cx {_fmt(center[0])} --cy {_fmt(center[1])}",
            "render_command": f"agentcad render {name} --section-z {_fmt(z)}",
            "probe": {"axis": "z", "position": z, "center": [center[0], center[1]]},
        }

    if check_type == "section_bbox_at_z":
        z = _num(check.get("z"))
        if z is None:
            return None
        region = _region(check.get("region"))
        command = f"agentcad probe {name} --z {_fmt(z)}"
        probe: dict[str, Any] = {"axis": "z", "position": z}
        if region:
            region_arg = _region_arg(region)
            command += f" --region {region_arg}"
            probe["region"] = [[region[0][0], region[0][1]], [region[1][0], region[1][1]]]
        return {
            "id": f"{check_id}_section_probe",
            "priority": 95,
            "source": "check",
            "feature": fid,
            "check": check_id,
            "check_type": check_type,
            "purpose": "verify solid/void evidence exactly where the contract samples the feature",
            "command": command,
            "render_command": f"agentcad render {name} --section-z {_fmt(z)}",
            "probe": probe,
        }

    if check_type == "min_wall_thickness":
        positions = _wall_sample_positions(check)
        if not positions:
            return None
        z = positions[len(positions) // 2]
        region = _region(check.get("region"))
        command = f"agentcad probe {name} --z {_fmt(z)}"
        if region:
            command += f" --section-region {_region_arg(region)}"
        return {
            "id": f"{check_id}_wall_probe",
            "priority": 95,
            "source": "check",
            "feature": fid,
            "check": check_id,
            "check_type": check_type,
            "purpose": "inspect the wall/root corridor at the most representative wall-thickness slice",
            "command": command,
            "render_command": f"agentcad render {name} --section-z {_fmt(z)}",
            "probe": {"axis": "z", "position": z, "sample_positions": positions},
        }

    if check_type == "hole_accessibility":
        axis = str(check.get("axis", "z")).lower()
        pos = _axis_position(check, axis)
        center = _pair(check.get("center"))
        if axis not in ("x", "y", "z") or pos is None:
            return None
        command = f"agentcad probe {name} --{axis} {_fmt(pos)}"
        if axis == "z" and center:
            command += f" --cx {_fmt(center[0])} --cy {_fmt(center[1])}"
        elif center:
            command += f" --point {_fmt(center[0])},{_fmt(center[1])}"
        return {
            "id": f"{check_id}_access_probe",
            "priority": 100,
            "source": "check",
            "feature": fid,
            "check": check_id,
            "check_type": check_type,
            "purpose": "inspect the real tool/fastener approach plane for obstructions",
            "command": command,
            "render_command": f"agentcad render {name} --section-{axis} {_fmt(pos)}",
            "probe": {"axis": axis, "position": pos, **({"center": list(center)} if center else {})},
        }

    if check_type == "min_clearance":
        section = _clearance_section(check)
        if section is None:
            return {
                "id": f"{check_id}_precheck",
                "priority": 90,
                "source": "check",
                "feature": fid,
                "check": check_id,
                "check_type": check_type,
                "purpose": "recompute declared edge-to-edge clearance before inspecting geometry",
                "command": f"agentcad precheck {name}",
                "probe": {"static": True},
            }
        z, region = section
        return {
            "id": f"{check_id}_clearance_probe",
            "priority": 90,
            "source": "check",
            "feature": fid,
            "check": check_id,
            "check_type": check_type,
            "purpose": "inspect the overlap plane where the declared clearance risk is highest",
            "command": f"agentcad probe {name} --z {_fmt(z)} --region {_region_arg(region)}",
            "render_command": f"agentcad render {name} --section-z {_fmt(z)}",
            "probe": {"axis": "z", "position": z, "region": [[region[0][0], region[0][1]], [region[1][0], region[1][1]]]},
        }

    if check_type == "feature_position":
        point = _triple(check.get("point"))
        if point is None:
            return None
        x, y, z = point
        return {
            "id": f"{check_id}_point_probe",
            "priority": 85,
            "source": "check",
            "feature": fid,
            "check": check_id,
            "check_type": check_type,
            "purpose": "inspect the exact solid/void point used by the contract",
            "command": f"agentcad probe {name} --z {_fmt(z)} --point {_fmt(x)},{_fmt(y)}",
            "render_command": f"agentcad render {name} --section-z {_fmt(z)}",
            "probe": {"axis": "z", "position": z, "point": [x, y]},
        }

    return None


def _probe_for_missing_evidence(
    name: str,
    fid: str,
    missing: str,
    categories: set[str],
    *,
    params: dict[str, Any],
    metadata: dict[str, Any],
    geometry: dict[str, Any],
    validation: dict[str, Any],
    failure_modes: list[dict[str, Any]] | None = None,
) -> dict:
    metadata_probe = _metadata_probe(fid, metadata)
    z = _best_z(params, geometry, validation, metadata_probe)
    center = _best_center(params, geometry, metadata_probe)

    if missing == "access" or ("hole" in categories and missing in ("position", "dimensions")):
        axis = metadata_probe.get("axis", "z") if metadata_probe else "z"
        pos = metadata_probe.get("position", z) if metadata_probe else z
        command = f"agentcad probe {name} --{axis} {_fmt(pos)}"
        if axis == "z":
            command += f" --cx {_fmt(center[0])} --cy {_fmt(center[1])}"
        else:
            command += f" --point {_fmt(center[0])},{_fmt(center[1])}"
        return {
            "id": f"{fid}_{missing}_probe",
            "priority": 80,
            "source": "feature_evidence_matrix",
            "feature": fid,
            "failure_mode": _primary_failure_mode_id(failure_modes),
            "missing": missing,
            "purpose": f"collect evidence for missing {missing} coverage on a hole-like feature",
            "command": command,
            "render_command": f"agentcad render {name} --section-{axis} {_fmt(pos)}",
            "probe": {"axis": axis, "position": pos, "center": [center[0], center[1]]},
        }

    if missing == "interface_risk":
        return {
            "id": f"{fid}_interface_risk_precheck",
            "priority": 75,
            "source": "feature_evidence_matrix",
            "feature": fid,
            "failure_mode": _primary_failure_mode_id(failure_modes),
            "missing": missing,
            "purpose": "plan edge-to-edge clearance descriptors for the mating or assembly risk",
            "command": f"agentcad precheck {name}",
            "probe": {"static": True},
        }

    if missing == "wall":
        region = _bbox_region(geometry, pad=-0.25) or ((center[0] - 5.0, center[1] - 5.0), (center[0] + 5.0, center[1] + 5.0))
        return {
            "id": f"{fid}_wall_probe",
            "priority": 75,
            "source": "feature_evidence_matrix",
            "feature": fid,
            "failure_mode": _primary_failure_mode_id(failure_modes),
            "missing": missing,
            "purpose": "inspect the most likely thin-wall/root plane before writing a wall-thickness check",
            "command": f"agentcad probe {name} --z {_fmt(z)} --section-region {_region_arg(region)}",
            "render_command": f"agentcad render {name} --section-z {_fmt(z)}",
            "probe": {"axis": "z", "position": z, "region": [[region[0][0], region[0][1]], [region[1][0], region[1][1]]]},
        }

    region = _bbox_region(geometry, pad=-0.25)
    command = f"agentcad probe {name} --z {_fmt(z)}"
    probe: dict[str, Any] = {"axis": "z", "position": z}
    if region:
        command += f" --section-region {_region_arg(region)}"
        probe["region"] = [[region[0][0], region[0][1]], [region[1][0], region[1][1]]]
    else:
        command += f" --cx {_fmt(center[0])} --cy {_fmt(center[1])}"
        probe["center"] = [center[0], center[1]]
    return {
        "id": f"{fid}_{missing}_probe",
        "priority": 70,
        "source": "feature_evidence_matrix",
        "feature": fid,
        "failure_mode": _primary_failure_mode_id(failure_modes),
        "missing": missing,
        "purpose": f"collect evidence for missing {missing} coverage",
        "command": command,
        "render_command": f"agentcad render {name} --section-z {_fmt(z)}",
        "probe": probe,
    }


def _probe_for_failure_mode(
    name: str,
    fid: str,
    failure: dict[str, Any],
    *,
    params: dict[str, Any],
    metadata: dict[str, Any],
    geometry: dict[str, Any],
    validation: dict[str, Any],
    linked_checks: list[dict[str, Any]],
) -> dict | None:
    mode = _norm(str(failure.get("mode") or failure.get("id") or ""))
    failure_id = str(failure.get("id") or mode or "failure_mode")
    metadata_probe = _metadata_probe(fid, metadata)
    z = _best_z(params, geometry, validation, metadata_probe)
    center = _best_center(params, geometry, metadata_probe)
    linked_probe = _probe_facts_from_checks(linked_checks)
    if linked_probe.get("position") is not None:
        z = float(linked_probe["position"])
    if linked_probe.get("center") is not None:
        center = linked_probe["center"]

    if any(token in mode for token in ("shallowhole", "blindhole", "holedepth")):
        depth = _num(failure.get("expected_depth_mm")) or _param_by_words(params, {"hole_depth", "depth", "blind_depth"})
        target_z = float(depth) if depth is not None else z
        return {
            "id": f"{fid}_{failure_id}_depth_probe",
            "priority": 105,
            "source": "failure_mode",
            "feature": fid,
            "failure_mode": failure_id,
            "purpose": "inspect the blind-hole bottom/depth plane instead of only checking the mouth diameter",
            "command": f"agentcad probe {name} --z {_fmt(target_z)} --cx {_fmt(center[0])} --cy {_fmt(center[1])}",
            "render_command": f"agentcad render {name} --section-z {_fmt(target_z)}",
            "expected": {"hole_depth_mm": depth},
            "probe": {"axis": "z", "position": target_z, "center": [center[0], center[1]]},
        }

    if "edgebreakout" in mode:
        return {
            "id": f"{fid}_{failure_id}_edge_probe",
            "priority": 105,
            "source": "failure_mode",
            "feature": fid,
            "failure_mode": failure_id,
            "purpose": "measure nearest contour distance from the risky hole/interface center to catch edge breakout",
            "command": f"agentcad probe {name} --z {_fmt(z)} --point {_fmt(center[0])},{_fmt(center[1])}",
            "render_command": f"agentcad render {name} --section-z {_fmt(z)}",
            "expected": {"min_edge_clearance_mm": failure.get("min_edge_clearance_mm")},
            "probe": {"axis": "z", "position": z, "point": [center[0], center[1]]},
        }

    if "thinwall" in mode or "walltoothin" in mode:
        region = _bbox_region(geometry, pad=-0.25) or ((center[0] - 5.0, center[1] - 5.0), (center[0] + 5.0, center[1] + 5.0))
        return {
            "id": f"{fid}_{failure_id}_wall_probe",
            "priority": 100,
            "source": "failure_mode",
            "feature": fid,
            "failure_mode": failure_id,
            "purpose": "sample the likely minimum wall/root section for thin-wall evidence",
            "command": f"agentcad probe {name} --z {_fmt(z)} --section-region {_region_arg(region)}",
            "render_command": f"agentcad render {name} --section-z {_fmt(z)}",
            "expected": {"min_wall_mm": failure.get("min_wall_mm")},
            "probe": {"axis": "z", "position": z, "region": [[region[0][0], region[0][1]], [region[1][0], region[1][1]]]},
        }

    if any(token in mode for token in ("suspendedrib", "detachedrib", "floatingrib")):
        root_z = _num(failure.get("root_z")) or 0.0
        region = _bbox_region(geometry, pad=-0.25) or ((center[0] - 5.0, center[1] - 5.0), (center[0] + 5.0, center[1] + 5.0))
        return {
            "id": f"{fid}_{failure_id}_root_probe",
            "priority": 100,
            "source": "failure_mode",
            "feature": fid,
            "failure_mode": failure_id,
            "purpose": "inspect the rib root plane to prove the rib is attached to parent material",
            "command": f"agentcad probe {name} --z {_fmt(root_z)} --section-region {_region_arg(region)}",
            "render_command": f"agentcad render {name} --section-z {_fmt(root_z)}",
            "probe": {"axis": "z", "position": root_z, "region": [[region[0][0], region[0][1]], [region[1][0], region[1][1]]]},
        }

    if any(token in mode for token in ("assemblyeccentricity", "eccentricity", "axismisalignment")):
        axis = metadata_probe.get("axis", "z") if metadata_probe else "z"
        pos = metadata_probe.get("position", z) if metadata_probe else z
        return {
            "id": f"{fid}_{failure_id}_axis_probe",
            "priority": 95,
            "source": "failure_mode",
            "feature": fid,
            "failure_mode": failure_id,
            "purpose": "inspect the interface axis/center used by assembly eccentricity checks",
            "command": f"agentcad probe {name} --{axis} {_fmt(pos)} --point {_fmt(center[0])},{_fmt(center[1])}",
            "render_command": f"agentcad render {name} --section-{axis} {_fmt(pos)}",
            "probe": {"axis": axis, "position": pos, "point": [center[0], center[1]]},
        }

    if "blocked" in mode or "access" in mode:
        axis = metadata_probe.get("axis", "z") if metadata_probe else "z"
        pos = metadata_probe.get("position", z) if metadata_probe else z
        command = f"agentcad probe {name} --{axis} {_fmt(pos)}"
        if axis == "z":
            command += f" --cx {_fmt(center[0])} --cy {_fmt(center[1])}"
        else:
            command += f" --point {_fmt(center[0])},{_fmt(center[1])}"
        return {
            "id": f"{fid}_{failure_id}_access_probe",
            "priority": 95,
            "source": "failure_mode",
            "feature": fid,
            "failure_mode": failure_id,
            "purpose": "inspect the declared access corridor for obstruction",
            "command": command,
            "render_command": f"agentcad render {name} --section-{axis} {_fmt(pos)}",
            "probe": {"axis": axis, "position": pos, "center": [center[0], center[1]]},
        }

    return None


def _metadata_probe(fid: str, metadata: dict[str, Any]) -> dict[str, Any]:
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

    axis = iface.get("axis")
    if isinstance(axis, dict):
        point = _triple(axis.get("point"))
        direction = _triple(axis.get("direction"))
        if point and direction:
            axis_name = _dominant_axis(direction)
            position, center = _axis_position_and_center(axis_name, point)
            return {"axis": axis_name, "position": position, "center": center}

    for key in ("inner_cylinder", "outer_cylinder"):
        desc = iface.get(key)
        if isinstance(desc, dict) and desc.get("type") == "cylinder":
            axis_name = str(desc.get("axis", "z")).lower()
            rng = desc.get(f"{axis_name}_range")
            center = _pair(desc.get("center"))
            if axis_name in ("x", "y", "z") and center:
                pos = _mid_pair(rng) if isinstance(rng, list) else 0.0
                return {"axis": axis_name, "position": pos, "center": center}
    return {}


def _probe_facts_from_checks(checks: list[dict[str, Any]]) -> dict[str, Any]:
    for check in checks:
        check_type = str(check.get("type") or "")
        if check_type in ("inner_diameter_at_z", "outer_diameter_at_z", "section_bbox_at_z"):
            z = _num(check.get("z"))
            center = _pair(check.get("center"))
            facts: dict[str, Any] = {}
            if z is not None:
                facts["position"] = z
            if center is not None:
                facts["center"] = center
            if facts:
                return facts
        if check_type == "hole_accessibility":
            axis = str(check.get("axis", "z")).lower()
            pos = _axis_position(check, axis)
            center = _pair(check.get("center"))
            facts = {}
            if pos is not None:
                facts["position"] = pos
            if center is not None:
                facts["center"] = center
            if facts:
                return facts
        if check_type == "feature_position":
            point = _triple(check.get("point"))
            if point is not None:
                return {"position": point[2], "center": (point[0], point[1])}
    return {}


def _clearance_section(check: dict[str, Any]) -> tuple[float, tuple[tuple[float, float], tuple[float, float]]] | None:
    shape_a = check.get("feature_a") or check.get("a")
    shape_b = check.get("feature_b") or check.get("b")
    if not isinstance(shape_a, dict) or not isinstance(shape_b, dict):
        return None
    try:
        aabb_a = shape_aabb(shape_a)
        aabb_b = shape_aabb(shape_b)
    except (KeyError, TypeError, ValueError):
        return None
    z0 = max(float(aabb_a["min"][2]), float(aabb_b["min"][2]))
    z1 = min(float(aabb_a["max"][2]), float(aabb_b["max"][2]))
    if z1 < z0:
        z0 = min(float(aabb_a["max"][2]), float(aabb_b["max"][2]))
        z1 = max(float(aabb_a["min"][2]), float(aabb_b["min"][2]))
    z = (z0 + z1) / 2.0
    x0 = min(float(aabb_a["min"][0]), float(aabb_b["min"][0]))
    x1 = max(float(aabb_a["max"][0]), float(aabb_b["max"][0]))
    y0 = min(float(aabb_a["min"][1]), float(aabb_b["min"][1]))
    y1 = max(float(aabb_a["max"][1]), float(aabb_b["max"][1]))
    pad = 1.0
    return z, ((x0 - pad, y0 - pad), (x1 + pad, y1 + pad))


def _wall_sample_positions(check: dict[str, Any]) -> list[float]:
    z = _num(check.get("z"))
    if z is not None:
        return [z]
    raw_range = check.get("range")
    if not isinstance(raw_range, list) or len(raw_range) != 2:
        return []
    start = _num(raw_range[0])
    end = _num(raw_range[1])
    if start is None or end is None:
        return []
    mid = (start + end) / 2.0
    return [start, mid, end]


def _interesting_step_changes(
    geometry: dict[str, Any],
    validation: dict[str, Any],
    observability: dict[str, Any],
) -> list[dict[str, Any]]:
    for source in (
        (validation.get("auto_scan") or {}).get("step_changes"),
        ((observability.get("scan") or {}).get("step_changes") if isinstance(observability, dict) else None),
        ((geometry.get("structure") or {}).get("step_changes") if isinstance(geometry, dict) else None),
    ):
        if isinstance(source, list):
            return [s for s in source if isinstance(s, dict)]
    return []


def _best_z(
    params: dict[str, Any],
    geometry: dict[str, Any],
    validation: dict[str, Any],
    metadata_probe: dict[str, Any],
) -> float:
    if metadata_probe and _num(metadata_probe.get("position")) is not None:
        return float(metadata_probe["position"])
    steps = _interesting_step_changes(geometry, validation, {})
    for step in steps:
        pos = _num(step.get("pos"))
        if pos is not None:
            return pos
    bbox = ((geometry.get("geometry") or {}).get("bbox") or {}) if isinstance(geometry, dict) else {}
    center = bbox.get("center")
    if isinstance(center, list) and len(center) >= 3 and _num(center[2]) is not None:
        return float(center[2])
    for key in ("height", "thickness", "wall_thickness", "plate_thickness"):
        val = _num(params.get(key))
        if val is not None:
            return val / 2.0
    return 0.0


def _best_center(
    params: dict[str, Any],
    geometry: dict[str, Any],
    metadata_probe: dict[str, Any],
) -> tuple[float, float]:
    if metadata_probe and _pair(metadata_probe.get("center")):
        center = _pair(metadata_probe.get("center"))
        assert center is not None
        return center
    bbox = ((geometry.get("geometry") or {}).get("bbox") or {}) if isinstance(geometry, dict) else {}
    center = bbox.get("center")
    if isinstance(center, list) and len(center) >= 2:
        x = _num(center[0])
        y = _num(center[1])
        if x is not None and y is not None:
            return x, y
    x = _num(params.get("center_x")) or _num(params.get("cx")) or 0.0
    y = _num(params.get("center_y")) or _num(params.get("cy")) or 0.0
    return x, y


def _bbox_region(
    geometry: dict[str, Any],
    *,
    pad: float = 0.0,
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    bbox = ((geometry.get("geometry") or {}).get("bbox") or {}) if isinstance(geometry, dict) else {}
    mn = bbox.get("min")
    mx = bbox.get("max")
    if not isinstance(mn, list) or not isinstance(mx, list) or len(mn) < 2 or len(mx) < 2:
        return None
    x0 = _num(mn[0])
    y0 = _num(mn[1])
    x1 = _num(mx[0])
    y1 = _num(mx[1])
    if None in (x0, y0, x1, y1):
        return None
    return ((float(x0) - pad, float(y0) - pad), (float(x1) + pad, float(y1) + pad))


def _dedupe_probe_suggestions(suggestions: list[dict]) -> list[dict]:
    deduped: dict[str, dict] = {}
    for item in suggestions:
        command = str(item.get("command") or item.get("id") or "")
        if not command:
            continue
        item = _normalize_probe_suggestion(item)
        current = deduped.get(command)
        if current is None or int(item.get("priority", 0)) > int(current.get("priority", 0)):
            deduped[command] = item
    return sorted(deduped.values(), key=lambda s: int(s.get("priority", 0)), reverse=True)


def _normalize_probe_suggestion(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    priority = int(normalized.get("priority", 0))
    normalized.setdefault("information_gain", _information_gain(priority))
    if "feature" in normalized:
        normalized.setdefault("linked_feature", normalized.get("feature"))
    if "failure_mode" in normalized and normalized.get("failure_mode"):
        normalized.setdefault("linked_failure_mode", normalized.get("failure_mode"))
    commands = []
    for key in ("command", "render_command", "precheck_command"):
        value = normalized.get(key)
        if isinstance(value, str) and value and value not in commands:
            commands.append(value)
    if commands:
        normalized["commands"] = commands
    return normalized


def _information_gain(priority: int) -> str:
    if priority >= 90:
        return "high"
    if priority >= 70:
        return "medium"
    return "low"


def _failure_modes_by_feature(design: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    raw = design.get("failure_modes") or []
    if isinstance(raw, dict):
        iterable = [
            {"id": key, **value} if isinstance(value, dict) and "id" not in value else value
            for key, value in raw.items()
        ]
    elif isinstance(raw, list):
        iterable = raw
    else:
        iterable = []
    for failure in iterable:
        if not isinstance(failure, dict):
            continue
        refs = []
        for key in ("affects", "feature_ids", "features"):
            value = failure.get(key)
            if isinstance(value, list):
                refs.extend(str(item) for item in value if isinstance(item, str))
        for key in ("feature", "feature_id"):
            if isinstance(failure.get(key), str):
                refs.append(str(failure[key]))
        for fid in refs:
            grouped.setdefault(fid, []).append(failure)
    return grouped


def _primary_failure_mode_id(failure_modes: list[dict[str, Any]] | None) -> str | None:
    if not failure_modes:
        return None
    first = failure_modes[0]
    return str(first.get("id") or first.get("mode") or "") or None


def _param_by_words(params: dict[str, Any], words: set[str]) -> float | None:
    for key, value in params.items():
        key_norm = _norm(str(key))
        if any(_norm(word) in key_norm for word in words):
            num = _num(value)
            if num is not None:
                return num
    return None


def _axis_position(check: dict[str, Any], axis: str) -> float | None:
    for key in ("position", axis, "z" if axis == "z" else ""):
        if not key:
            continue
        value = _num(check.get(key))
        if value is not None:
            return value
    return None


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
