"""Unified geometric inspection: three-axis scans, standard section SVGs, suggested probes."""
from __future__ import annotations

from pathlib import Path

from .section import AXIS_X, AXIS_Y, AXIS_Z, scan_profile, write_section_svg
from .stl import mesh_report, read_stl
from .workspace import outputs_dir


def inspect_model(project: Path, name: str, scan_samples: int = 20) -> dict:
    """Run a comprehensive geometric inspection of a built model.

    Performs three-axis profile scans (X, Y, Z), generates cross-section SVGs
    at detected step changes and at the midpoint of each axis, and assembles
    actionable ``suggested_next`` probe commands.

    All output is JSON — no HTML.  Section SVG paths are listed in ``sections``
    so the caller can read them with vision tools as needed.

    Args:
        project: Project root path.
        name: Model name.
        scan_samples: Number of samples per axis scan (default 20).
    """
    stl_path = outputs_dir(project, name) / f"{name}.stl"
    if not stl_path.exists():
        return {
            "ok": False,
            "stage": "inspect",
            "model": name,
            "error": {
                "type": "STLMissing",
                "message": f"STL not found — run 'cad build {name}' first: {stl_path}",
            },
        }

    triangles = read_stl(stl_path)
    out_dir = outputs_dir(project, name)
    report = mesh_report(triangles)

    # ── Three-axis scans ───────────────────────────────────────────────────────
    scans: dict[str, dict] = {}
    for axis_int, axis_name in ((AXIS_Z, "z"), (AXIS_X, "x"), (AXIS_Y, "y")):
        scan = scan_profile(triangles, axis=axis_int, samples=scan_samples, step_threshold=3.0)
        scans[axis_name] = scan

    # ── Standard section SVGs ─────────────────────────────────────────────────
    # For each axis: midpoint + step change positions
    sections: dict[str, str] = {}

    def _write(axis_int: int, axis_name: str, value: float, label: str) -> None:
        svg_path = out_dir / f"section.{axis_name}{value:.2f}.svg"
        info = write_section_svg(triangles, axis_int, value, svg_path)
        sections[label] = info["svg"]

    for axis_int, axis_name in ((AXIS_Z, "z"), (AXIS_X, "x"), (AXIS_Y, "y")):
        scan = scans[axis_name]
        if not scan.get("ok"):
            continue
        lo, hi = scan["pos_range"]
        mid = (lo + hi) / 2
        _write(axis_int, axis_name, mid, f"{axis_name}_mid")
        for step in scan.get("step_changes", []):
            pos = step["pos"]
            key = f"{axis_name}_{pos:.2f}".replace(".", "_")
            _write(axis_int, axis_name, pos, key)

    # ── Suggested next actions ────────────────────────────────────────────────
    suggested_next: list[dict] = []
    for axis_name in ("z", "x", "y"):
        scan = scans.get(axis_name, {})
        for step in scan.get("step_changes", []):
            pos = step["pos"]
            axis_flag = f"--{axis_name}"
            suggested_next.append({
                "action": "probe",
                "axis": axis_name.upper(),
                "pos": pos,
                "hint": step.get("hint", ""),
                "command": f"cad probe {name} {axis_flag} {pos} --json",
            })

    bbox = (report.get("bbox") or {})
    center = bbox.get("center") or [0.0, 0.0, 0.0]
    suggested_next.append({
        "action": "probe",
        "axis": "Z",
        "pos": center[2],
        "hint": "Z midpoint — probe inner/outer diameter at model centre",
        "command": f"cad probe {name} --z {center[2]:.2f} \"--center={center[0]:.1f},{center[1]:.1f}\" --json",
    })

    return {
        "ok": True,
        "stage": "inspect",
        "model": name,
        "geometry": report,
        "scans": scans,
        "sections": sections,
        "suggested_next": suggested_next,
    }
