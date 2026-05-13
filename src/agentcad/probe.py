from __future__ import annotations

from pathlib import Path
from typing import Any

from .contract import classify_feature, evaluate_feature_evidence_matrix_dict
from .geometry import shape_aabb
from .jsonio import read_json
from .section import (
    AXIS_X,
    AXIS_Y,
    AXIS_Z,
    analyze_section_segments,
    query_section_measurements,
    scan_profile,
    section_segments,
)
from .stl import read_stl, section_bbox_at_z, section_radius_at_z
from .workspace import model_dir, outputs_dir

_AXIS_MAP = {"x": AXIS_X, "y": AXIS_Y, "z": AXIS_Z}
_AXIS_NAME = {AXIS_X: "X", AXIS_Y: "Y", AXIS_Z: "Z"}


def plan_probes(project: Path, name: str) -> dict:
    """Suggest high-value probe/render commands from contract and artifacts."""
    mdir = model_dir(project, name)
    design = read_json(mdir / "design.json", default=None)
    if not isinstance(design, dict):
        return {
            "ok": False,
            "stage": "probe-plan",
            "model": name,
            "suggested_probes": [],
            "error": {
                "type": "DesignNotFound",
                "message": f"design.json not found for model '{name}'",
            },
        }

    out_dir = outputs_dir(project, name)
    params = read_json(mdir / "params.json", default={}) or {}
    metadata = read_json(mdir / "metadata.json", default={}) or {}
    geometry = read_json(out_dir / "geometry.json", default={}) or {}
    validation = read_json(out_dir / "validation.json", default={}) or {}
    observability = read_json(out_dir / "observability.json", default={}) or {}
    matrix = evaluate_feature_evidence_matrix_dict(design)
    suggested = plan_probe_points(
        name,
        design,
        params=params,
        metadata=metadata,
        geometry=geometry,
        validation=validation,
        observability=observability,
        feature_evidence_matrix=matrix,
    )
    return {
        "ok": True,
        "stage": "probe-plan",
        "model": name,
        "suggested_probes": suggested,
        "feature_evidence_matrix": matrix,
    }


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


def probe_model(
    project: Path,
    name: str,
    z_values: list[float] | None = None,
    x_values: list[float] | None = None,
    y_values: list[float] | None = None,
    center: tuple[float, float] = (0.0, 0.0),
    region: tuple[tuple[float, float], tuple[float, float]] | None = None,
    section_region: tuple[tuple[float, float], tuple[float, float]] | None = None,
    line_u: float | None = None,
    line_v: float | None = None,
    point: tuple[float, float] | None = None,
) -> dict:
    """Probe STL geometry at one or more cross-sections along any axis.

    Supports Z sections (radial + region analysis) and X/Y sections (bbox analysis).
    Returns ``suggested_checks`` — ready-to-paste snippets for design.json.

    Args:
        project: Project root path.
        name: Model name.
        z_values: Z heights to probe (radial measurement with optional region).
        x_values: X positions to probe (YZ plane bbox).
        y_values: Y positions to probe (XZ plane bbox).
        center: (cx, cy) for radial Z measurements.
        region: Optional ((x_min, y_min), (x_max, y_max)) for bbox region check.
        section_region: Optional region in the active section plane.
        line_u: Optional fixed U coordinate for line-intersection measurement.
        line_v: Optional fixed V coordinate for line-intersection measurement.
        point: Optional point in section coordinates for nearest-contour distance.
    """
    stl_path = outputs_dir(project, name) / f"{name}.stl"
    if not stl_path.exists():
        return {
            "ok": False,
            "stage": "probe",
            "model": name,
            "error": {
                "type": "STLMissing",
                "message": f"STL not found — run 'agentcad build {name}' first: {stl_path}",
            },
        }

    triangles = read_stl(stl_path)
    all_results: list[dict] = []

    # Z probes — radial measurements
    for z in (z_values or []):
        all_results.append(_probe_z(
            triangles, z, center, region,
            section_region=section_region,
            line_u=line_u,
            line_v=line_v,
            point=point,
        ))

    # X probes — YZ plane bbox
    for x in (x_values or []):
        all_results.append(_probe_axis(
            triangles, AXIS_X, x,
            section_region=section_region,
            line_u=line_u,
            line_v=line_v,
            point=point,
        ))

    # Y probes — XZ plane bbox
    for y in (y_values or []):
        all_results.append(_probe_axis(
            triangles, AXIS_Y, y,
            section_region=section_region,
            line_u=line_u,
            line_v=line_v,
            point=point,
        ))

    total = len(all_results)
    if total == 0:
        return {"ok": False, "stage": "probe", "model": name,
                "error": {"type": "NoProbe", "message": "specify at least one of --z, --x, --y"}}

    cx, cy = center
    payload: dict = {
        "ok": True,
        "stage": "probe",
        "model": name,
        "center": [cx, cy],
    }
    if total == 1:
        r = all_results[0]
        payload.update(r)
    else:
        payload["results"] = all_results

    return payload


def probe_scan(
    project: Path,
    name: str,
    axis: str = "z",
    samples: int = 20,
) -> dict:
    """Scan the model along an axis and report cross-section profile.

    Detects step changes (geometry transitions) and suggests probe commands
    for investigating interesting positions further.

    Args:
        project: Project root path.
        name: Model name.
        axis: "x", "y", or "z".
        samples: Number of cross-sections to sample.
    """
    stl_path = outputs_dir(project, name) / f"{name}.stl"
    if not stl_path.exists():
        return {
            "ok": False,
            "stage": "probe",
            "model": name,
            "error": {
                "type": "STLMissing",
                "message": f"STL not found — run 'agentcad build {name}' first: {stl_path}",
            },
        }

    axis_int = _AXIS_MAP.get(axis.lower(), AXIS_Z)
    triangles = read_stl(stl_path)
    scan = scan_profile(triangles, axis=axis_int, samples=samples)

    if not scan.get("ok"):
        return {"ok": False, "stage": "probe", "model": name, "error": scan.get("error")}

    # Build suggested probe commands for each step change
    suggested = []
    for step in scan.get("step_changes", []):
        pos = step["pos"]
        if axis_int == AXIS_Z:
            cmd = f"agentcad probe {name} --z {pos}"
        elif axis_int == AXIS_X:
            cmd = f"agentcad probe {name} --x {pos}"
        else:
            cmd = f"agentcad probe {name} --y {pos}"
        suggested.append({
            "pos": pos,
            "hint": step.get("hint", ""),
            "command": cmd,
        })

    return {
        "ok": True,
        "stage": "probe",
        "model": name,
        "scan": scan,
        "suggested_probes": suggested,
    }


# ── Probe planning helpers ───────────────────────────────────────────────────

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
        "missing": missing,
        "purpose": f"collect evidence for missing {missing} coverage",
        "command": command,
        "render_command": f"agentcad render {name} --section-z {_fmt(z)}",
        "probe": probe,
    }


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
        current = deduped.get(command)
        if current is None or int(item.get("priority", 0)) > int(current.get("priority", 0)):
            deduped[command] = item
    return sorted(deduped.values(), key=lambda s: int(s.get("priority", 0)), reverse=True)


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


def _region(value: Any) -> tuple[tuple[float, float], tuple[float, float]] | None:
    if not isinstance(value, list) or len(value) != 2:
        return None
    first = _pair(value[0])
    second = _pair(value[1])
    if first is None or second is None:
        return None
    return first, second


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


def _mid_pair(value: Any) -> float:
    pair = _pair(value)
    if pair is None:
        return 0.0
    return (pair[0] + pair[1]) / 2.0


def _num(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _region_arg(region: tuple[tuple[float, float], tuple[float, float]]) -> str:
    return ",".join(_fmt(v) for v in (region[0][0], region[0][1], region[1][0], region[1][1]))


def _fmt(value: float) -> str:
    return f"{float(value):.4f}".rstrip("0").rstrip(".")


def _norm(value: Any) -> str:
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


# ── Internal helpers ──────────────────────────────────────────────────────────

def _probe_z(
    triangles: list,
    z: float,
    center: tuple[float, float],
    region: tuple[tuple[float, float], tuple[float, float]] | None,
    section_region: tuple[tuple[float, float], tuple[float, float]] | None,
    line_u: float | None,
    line_v: float | None,
    point: tuple[float, float] | None,
) -> dict:
    cx, cy = center
    section = section_radius_at_z(triangles, z, center=center)
    entry: dict = {"axis": "Z", "pos": z, "z": z, "section": section}
    segs = section_segments(triangles, AXIS_Z, z)
    entry["section_analysis"] = analyze_section_segments(segs, AXIS_Z, z)
    measurements = query_section_measurements(
        segs,
        AXIS_Z,
        z,
        region=section_region,
        line_u=line_u,
        line_v=line_v,
        point=point,
    )
    if measurements:
        entry["measurements"] = measurements

    if section.get("ok"):
        outer_d = section.get("diameter_outer_estimate")
        inner_d = section.get("diameter_inner_estimate")
        suggested: dict = {}
        if outer_d is not None:
            suggested["outer_diameter_at_z"] = {
                "type": "outer_diameter_at_z",
                "z": z, "center": [cx, cy],
                "expected": round(outer_d, 2), "tolerance": 1.0,
            }
        if inner_d is not None and inner_d > 0.5:
            suggested["inner_diameter_at_z"] = {
                "type": "inner_diameter_at_z",
                "z": z, "center": [cx, cy],
                "expected": round(inner_d, 2), "tolerance": 2.0,
            }
        if region is not None:
            bbox_section = section_bbox_at_z(triangles, z, region=region)
            has_pts = bbox_section.get("region_has_points", False)
            (rx0, ry0), (rx1, ry1) = region
            entry["region_section"] = bbox_section
            suggested["section_bbox_at_z"] = {
                "type": "section_bbox_at_z",
                "z": z,
                "region": [[rx0, ry0], [rx1, ry1]],
                "expected": "solid" if has_pts else "void",
            }
        entry["suggested_checks"] = suggested
    else:
        entry["error"] = section.get("error", "no intersections at this Z")

    return entry


def _probe_axis(
    triangles: list,
    axis: int,
    value: float,
    section_region: tuple[tuple[float, float], tuple[float, float]] | None,
    line_u: float | None,
    line_v: float | None,
    point: tuple[float, float] | None,
) -> dict:
    """Probe a non-Z axis: report the YZ or XZ bounding box."""
    segs = section_segments(triangles, axis, value)
    axis_name = _AXIS_NAME[axis]
    entry: dict = {"axis": axis_name, "pos": value}
    analysis = analyze_section_segments(segs, axis, value)
    entry["section_analysis"] = analysis
    measurements = query_section_measurements(
        segs,
        axis,
        value,
        region=section_region,
        line_u=line_u,
        line_v=line_v,
        point=point,
    )
    if measurements:
        entry["measurements"] = measurements

    if not segs:
        entry["error"] = f"no intersections at {axis_name}={value}"
        return entry

    bbox = analysis["bbox"]
    entry["section"] = {
        "ok": True,
        "u_size": round(bbox["u_size"], 3),
        "v_size": round(bbox["v_size"], 3),
        "u_min": round(bbox["u_min"], 3),
        "u_max": round(bbox["u_max"], 3),
        "v_min": round(bbox["v_min"], 3),
        "v_max": round(bbox["v_max"], 3),
        "segment_count": len(segs),
    }
    return entry
