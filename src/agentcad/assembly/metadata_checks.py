from __future__ import annotations

from typing import Any

from ..contract import SchemaIssue
from ..stl import section_radius_at_z
from .references import _descriptor_radius, _is_cylinder_descriptor


def _metadata_schema_checks(components: dict[str, dict]) -> list[dict]:
    """Convert metadata interface validation issues into assembly validation checks."""
    checks: list[dict] = []
    for cid, record in components.items():
        issues = record.get("metadata_issues") or []
        if not issues:
            continue
        error_issues = [i for i in issues if isinstance(i, SchemaIssue) and i.severity != "warning"]
        warning_issues = [i for i in issues if isinstance(i, SchemaIssue) and i.severity == "warning"]
        if error_issues:
            checks.append({
                "name": f"metadata_schema:{cid}",
                "type": "metadata_schema",
                "ok": False,
                "component": cid,
                "issues": [{"path": i.path, "message": i.message, "severity": i.severity, **({"hint": i.hint} if i.hint else {})} for i in error_issues],
                "hint": "fix metadata.json interface/anchor schema errors before assembly validation",
            })
        elif warning_issues:
            checks.append({
                "name": f"metadata_schema:{cid}",
                "type": "metadata_schema",
                "ok": True,
                "component": cid,
                "warnings": [{"path": i.path, "message": i.message, "severity": i.severity, **({"hint": i.hint} if i.hint else {})} for i in warning_issues],
            })
    return checks


def _evaluate_metadata_geometry(resolved_refs: dict[str, dict], components: dict[str, dict]) -> list[dict]:
    checks = []
    for ref, resolved in resolved_refs.items():
        if not resolved.get("ok"):
            checks.append(
                {
                    "name": f"reference_resolves:{ref}",
                    "type": "reference_resolves",
                    "ok": False,
                    "ref": ref,
                    "error": resolved.get("error"),
                }
            )
            continue
        local = resolved.get("local")
        for path, desc in _iter_cylinder_descriptors(local, prefix=ref):
            check = _check_cylinder_descriptor(path, desc, components[resolved["component"]])
            checks.append(check)
    return checks


def _iter_cylinder_descriptors(value: Any, prefix: str) -> list[tuple[str, dict]]:
    if _is_cylinder_descriptor(value):
        return [(prefix, value)]
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, dict):
                found.extend(_iter_cylinder_descriptors(item, f"{prefix}.{key}"))
    return found


def _check_cylinder_descriptor(ref: str, desc: dict, component: dict) -> dict:
    radius = _descriptor_radius(desc)
    if radius is None:
        return {
            "name": f"interface_geometry_consistency:{ref}",
            "type": "interface_geometry_consistency",
            "ok": False,
            "ref": ref,
            "error": {"type": "RadiusMissing", "message": "cylinder descriptor must include radius_mm or diameter_mm"},
        }
    if desc.get("axis", "z") != "z":
        return {
            "name": f"interface_geometry_consistency:{ref}",
            "type": "interface_geometry_consistency",
            "ok": False,
            "ref": ref,
            "error": {"type": "UnsupportedAxis", "message": "MVP cylinder STL measurement supports local Z axis only"},
        }
    z_range = desc.get("z_range") or desc.get("range")
    if not isinstance(z_range, (list, tuple)) or len(z_range) != 2:
        return {
            "name": f"interface_geometry_consistency:{ref}",
            "type": "interface_geometry_consistency",
            "ok": False,
            "ref": ref,
            "error": {"type": "RangeMissing", "message": "cylinder descriptor must include z_range"},
        }
    z = (float(z_range[0]) + float(z_range[1])) / 2.0
    center = desc.get("center", [0.0, 0.0])
    if not isinstance(center, (list, tuple)) or len(center) < 2:
        center = [0.0, 0.0]
    section = section_radius_at_z(component.get("local_triangles") or [], z, center=(float(center[0]), float(center[1])))
    surface = str(desc.get("surface") or _infer_surface(ref)).lower()
    measured_radius = section.get("radius_inner_estimate") if surface == "inner" else section.get("radius_outer_estimate")
    tol = float(desc.get("tolerance_mm", desc.get("metadata_tolerance_mm", 0.25)))
    ok = bool(section.get("ok")) and measured_radius is not None and abs(float(measured_radius) - radius) <= tol
    return {
        "name": f"interface_geometry_consistency:{ref}",
        "type": "interface_geometry_consistency",
        "ok": ok,
        "ref": ref,
        "component": component["id"],
        "surface": surface,
        "expected_radius_mm": radius,
        "measured_radius_mm": float(measured_radius) if measured_radius is not None else None,
        "delta_mm": abs(float(measured_radius) - radius) if measured_radius is not None else None,
        "tolerance_mm": tol,
        "section": section,
    }


def _infer_surface(ref: str) -> str:
    return "inner" if ".inner" in ref or "inner_" in ref or ".recess" in ref else "outer"
