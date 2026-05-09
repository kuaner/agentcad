from __future__ import annotations

from pathlib import Path

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
from .workspace import outputs_dir

_AXIS_MAP = {"x": AXIS_X, "y": AXIS_Y, "z": AXIS_Z}
_AXIS_NAME = {AXIS_X: "X", AXIS_Y: "Y", AXIS_Z: "Z"}


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
            cmd = f"agentcad probe {name} --z {pos} --json"
        elif axis_int == AXIS_X:
            cmd = f"agentcad probe {name} --x {pos} --json"
        else:
            cmd = f"agentcad probe {name} --y {pos} --json"
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
        region=section_region or region,
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
