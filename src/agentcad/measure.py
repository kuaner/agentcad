from __future__ import annotations

from pathlib import Path

from .jsonio import write_json
from .stl import mesh_report, read_stl
from .workspace import outputs_dir


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
        "artifacts": {"geometry": str(report_path)},
        "message": "model measured",
    }
    write_json(report_path, payload)
    return payload
