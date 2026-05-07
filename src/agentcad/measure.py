from __future__ import annotations

from pathlib import Path

from .jsonio import write_json
from .section import AXIS_Z, scan_profile
from .stl import mesh_report, read_stl
from .workspace import outputs_dir


def _structure_from_scan(triangles: list, report: dict) -> dict:
    """Derive high-level structural facts from a quick Z-axis scan.

    Returns a ``structure`` dict with:
      - ``has_internal_void``: True when the Z scan detects a step change
        that indicates a cavity, shell, or hollow region.
      - ``void_start_z``: approximate Z where the inner cavity begins (first
        significant negative step change), or None.
      - ``step_changes``: all detected Z-axis step changes.
    """
    scan = scan_profile(triangles, axis=AXIS_Z, samples=16, step_threshold=3.0)
    if not scan.get("ok"):
        return {"has_internal_void": False, "void_start_z": None, "step_changes": []}

    steps = scan.get("step_changes", [])
    # A significant negative step (section shrinks) indicates a cavity or shell wall.
    negative_steps = [s for s in steps if s["delta_u"] < -3.0 or s["delta_v"] < -3.0]
    has_void = len(negative_steps) > 0
    void_start_z = negative_steps[0]["pos"] if negative_steps else None
    return {
        "has_internal_void": has_void,
        "void_start_z": void_start_z,
        "step_changes": steps,
    }


def measure_model(project: Path, name: str) -> dict:
    out_dir = outputs_dir(project, name)
    stl_path = out_dir / f"{name}.stl"
    report_path = out_dir / "geometry.json"
    if not stl_path.exists():
        payload = {
            "ok": False,
            "stage": "measure",
            "model": name,
            "error": {
                "type": "ArtifactMissing",
                "message": f"missing STL artifact: {stl_path}",
                "file": str(stl_path),
            },
        }
        write_json(report_path, payload)
        return payload

    try:
        triangles = read_stl(stl_path)
        report = mesh_report(triangles)
        structure = _structure_from_scan(triangles, report)
    except Exception as exc:
        payload = {
            "ok": False,
            "stage": "measure",
            "model": name,
            "error": {"type": type(exc).__name__, "message": str(exc), "file": str(stl_path)},
        }
        write_json(report_path, payload)
        return payload

    payload = {
        "ok": True,
        "stage": "measure",
        "model": name,
        "source": str(stl_path),
        "geometry": report,
        "structure": structure,
        "artifacts": {"geometry": str(report_path)},
        "message": "model measured",
    }
    write_json(report_path, payload)
    return payload
