from __future__ import annotations

from pathlib import Path

from .stl import read_stl, section_bbox_at_z, section_radius_at_z
from .workspace import outputs_dir


def probe_model(
    project: Path,
    name: str,
    z_values: list[float],
    center: tuple[float, float] = (0.0, 0.0),
    region: tuple[tuple[float, float], tuple[float, float]] | None = None,
) -> dict:
    """Probe STL geometry at one or more Z cross-sections.

    Outputs radial envelope statistics and, optionally, region analysis.
    Also emits ``suggested_checks`` — ready-to-paste snippets for design.json
    that help agents write meaningful validation contracts without guessing
    expected values.

    Args:
        project: Project root path.
        name: Model name.
        z_values: One or more Z heights to probe.
        center: (cx, cy) for radial measurements.
        region: Optional ((x_min, y_min), (x_max, y_max)) for bbox region check.
    """
    stl_path = outputs_dir(project, name) / f"{name}.stl"
    if not stl_path.exists():
        return {
            "ok": False,
            "stage": "probe",
            "model": name,
            "error": {
                "type": "STLMissing",
                "message": f"STL not found — run 'cad build {name}' first: {stl_path}",
            },
        }

    triangles = read_stl(stl_path)
    cx, cy = center

    results = []
    for z in z_values:
        section = section_radius_at_z(triangles, z, center=center)
        entry: dict = {"z": z, "section": section}

        if section.get("ok"):
            outer_d = section.get("diameter_outer_estimate")
            inner_d = section.get("diameter_inner_estimate")
            suggested: dict = {}
            if outer_d is not None:
                suggested["outer_diameter_at_z"] = {
                    "type": "outer_diameter_at_z",
                    "z": z,
                    "center": [cx, cy],
                    "expected": round(outer_d, 2),
                    "tolerance": 1.0,
                }
            if inner_d is not None and inner_d > 0.5:
                suggested["inner_diameter_at_z"] = {
                    "type": "inner_diameter_at_z",
                    "z": z,
                    "center": [cx, cy],
                    "expected": round(inner_d, 2),
                    "tolerance": 2.0,
                }

            if region is not None:
                bbox_section = section_bbox_at_z(triangles, z, region=region)
                has_pts = bbox_section.get("region_has_points", False)
                entry["region_section"] = bbox_section
                (rx0, ry0), (rx1, ry1) = region
                suggested["section_bbox_at_z"] = {
                    "type": "section_bbox_at_z",
                    "z": z,
                    "region": [[rx0, ry0], [rx1, ry1]],
                    "expected": "solid" if has_pts else "void",
                }

            entry["suggested_checks"] = suggested
        else:
            entry["error"] = section.get("error", "no intersections at this Z")

        results.append(entry)

    single = len(z_values) == 1
    payload: dict = {
        "ok": True,
        "stage": "probe",
        "model": name,
        "center": [cx, cy],
    }
    if single:
        r = results[0]
        payload.update({k: v for k, v in r.items() if k != "z"})
        payload["z"] = z_values[0]
    else:
        payload["results"] = results
        payload["z_values"] = z_values

    return payload
