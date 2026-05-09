from __future__ import annotations

import itertools
import math
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .jsonio import read_json, write_json
from .render import triangles_to_svg
from .runner import build_model
from .stl import Triangle, Vec3, cross, dot, length, mesh_report, normalize, read_stl, section_radius_at_z, sub
from .workspace import model_dir, normalize_model_name, outputs_dir

ASSEMBLY_SCHEMA = "agentcad.assembly.v1"
GEOMETRY_SCHEMA = "agentcad.assembly.geometry.v1"
VALIDATION_SCHEMA = "agentcad.assembly.validation.v1"
OBSERVABILITY_SCHEMA = "agentcad.assembly.observability.v1"

EPS = 1e-6


class AssemblyError(Exception):
    def __init__(self, error_type: str, message: str):
        super().__init__(message)
        self.error_type = error_type
        self.message = message


@dataclass(frozen=True)
class Transform:
    translation: Vec3
    rotation_euler_deg: Vec3
    rotation: tuple[Vec3, Vec3, Vec3]
    matrix: list[list[float]]


def assemblies_dir(project: Path) -> Path:
    return project / "assemblies"


def assembly_dir(project: Path, name: str) -> Path:
    return assemblies_dir(project) / normalize_model_name(name)


def assembly_outputs_dir(project: Path, name: str) -> Path:
    return assembly_dir(project, name) / "outputs"


def init_assembly(project: Path, name: str, force: bool = False) -> dict:
    safe = normalize_model_name(name)
    root = assembly_dir(project, safe)
    contract_path = root / "assembly.json"
    if contract_path.exists() and not force:
        return {
            "ok": False,
            "stage": "assembly_init",
            "assembly": safe,
            "error": {"type": "AssemblyExists", "message": f"assembly exists: {safe}"},
        }

    payload = {
        "schema": ASSEMBLY_SCHEMA,
        "name": safe,
        "units": "mm",
        "intent": "",
        "components": [],
        "mates": [],
        "checks": [],
        "ignore_pairs": [],
    }
    write_json(contract_path, payload)
    assembly_outputs_dir(project, safe).mkdir(parents=True, exist_ok=True)
    return {
        "ok": True,
        "stage": "assembly_init",
        "assembly": safe,
        "path": str(root),
        "artifacts": {"assembly": str(contract_path)},
        "message": "assembly created",
    }


def list_assemblies(project: Path) -> dict:
    rows = []
    for contract_path in sorted(assemblies_dir(project).glob("*/assembly.json")):
        data = read_json(contract_path, default={}) or {}
        rows.append(
            {
                "name": data.get("name") or contract_path.parent.name,
                "path": str(contract_path.parent),
                "components": len(data.get("components") or []),
                "mates": len(data.get("mates") or []),
                "checks": len(data.get("checks") or []),
            }
        )
    return {"ok": True, "stage": "assembly_list", "assemblies": rows}


def measure_assembly(project: Path, name: str) -> dict:
    safe = normalize_model_name(name)
    out_dir = assembly_outputs_dir(project, safe)
    out_dir.mkdir(parents=True, exist_ok=True)
    geometry_path = out_dir / "assembly_geometry.json"

    try:
        contract, contract_path = _load_contract(project, safe)
        components = _load_components(project, contract)
        refs_needed = _collect_references(contract)
        resolved_refs = _resolve_references(refs_needed, components)
        metadata_checks = _evaluate_metadata_geometry(resolved_refs, components)
        mate_residuals = _evaluate_mates(contract, resolved_refs)
        pairwise = _measure_pairwise(components)
        assembly_bbox = _global_bbox([component["world_bbox"] for component in components.values()])

        geometry = {
            "ok": True,
            "schema": GEOMETRY_SCHEMA,
            "stage": "assembly_measure",
            "assembly": safe,
            "source": str(contract_path),
            "units": contract.get("units", "mm"),
            "components": {cid: _public_component_record(record) for cid, record in components.items()},
            "references": resolved_refs,
            "metadata_geometry_checks": metadata_checks,
            "mate_residuals": mate_residuals,
            "pairwise": pairwise,
            "assembly_geometry": {
                "component_count": len(components),
                "triangle_count": sum(record["triangle_count"] for record in components.values()),
                "bbox": assembly_bbox,
            },
            "artifacts": {"geometry": str(geometry_path)},
        }
        write_json(geometry_path, geometry)
        return geometry
    except AssemblyError as exc:
        payload = _failure(safe, "assembly_measure", exc.error_type, exc.message)
        payload["artifacts"] = {"geometry": str(geometry_path)}
        write_json(geometry_path, payload)
        return payload


def validate_assembly(project: Path, name: str) -> dict:
    safe = normalize_model_name(name)
    out_dir = assembly_outputs_dir(project, safe)
    out_dir.mkdir(parents=True, exist_ok=True)
    validation_path = out_dir / "assembly_validation.json"
    observability_path = out_dir / "assembly_observability.json"

    try:
        contract, _ = _load_contract(project, safe)
        geometry = measure_assembly(project, safe)
        if not geometry.get("ok"):
            payload = {
                **geometry,
                "stage": "assembly_validate",
                "artifacts": {
                    "geometry": str(out_dir / "assembly_geometry.json"),
                    "validation": str(validation_path),
                    "observability": str(observability_path),
                },
            }
            write_json(validation_path, payload)
            return payload

        checks: list[dict] = []
        checks.extend(_fresh_component_checks(geometry))
        checks.extend(geometry.get("metadata_geometry_checks") or [])
        checks.extend(_mate_checks(geometry))
        checks.extend(_evaluate_user_checks(contract, geometry))
        checks.extend(_fit_coverage_checks(contract, geometry))
        checks.extend(_component_pair_classification_checks(contract, geometry))

        render_payload = _render_assembly_previews(project, safe, geometry)
        checks.append(
            {
                "name": "assembly_previews_generated",
                "type": "artifact_exists",
                "ok": bool(render_payload.get("ok")),
                "artifacts": render_payload.get("artifacts", {}),
                "error": render_payload.get("error"),
            }
        )

        mjcf_payload = _export_mjcf(project, safe, contract, geometry)
        mjcf_check = _mjcf_consistency_check(mjcf_payload, geometry)
        checks.append(mjcf_check)
        checks.append(_transform_consistency_check(geometry, mjcf_payload))

        failed = [check for check in checks if not check.get("ok")]
        artifacts = {
            "geometry": str(out_dir / "assembly_geometry.json"),
            "validation": str(validation_path),
            "observability": str(observability_path),
        }
        artifacts.update(render_payload.get("artifacts") or {})
        artifacts.update(mjcf_payload.get("artifacts") or {})

        payload = {
            "ok": not failed,
            "schema": VALIDATION_SCHEMA,
            "stage": "assembly_validate",
            "assembly": safe,
            "summary": {
                "checks": len(checks),
                "passed": len(checks) - len(failed),
                "failed": len(failed),
            },
            "checks": checks,
            "geometry_summary": geometry.get("assembly_geometry"),
            "mate_residuals": geometry.get("mate_residuals", []),
            "pairwise": geometry.get("pairwise", []),
            "artifacts": artifacts,
            "message": "assembly validation passed" if not failed else "assembly validation failed",
        }
        write_json(validation_path, payload)
        _write_observability(observability_path, safe, geometry, payload)
        return payload
    except AssemblyError as exc:
        payload = _failure(safe, "assembly_validate", exc.error_type, exc.message)
        payload["artifacts"] = {"validation": str(validation_path)}
        write_json(validation_path, payload)
        return payload


def review_assembly(project: Path, name: str) -> dict:
    safe = normalize_model_name(name)
    out_dir = assembly_outputs_dir(project, safe)
    validation_path = out_dir / "assembly_validation.json"
    observability_path = out_dir / "assembly_observability.json"
    review_path = out_dir / "assembly_review.json"

    validation = read_json(validation_path, default=None)
    observability = read_json(observability_path, default=None)
    checks = []
    checks.append(
        {
            "name": "assembly_validation_present",
            "type": "artifact_exists",
            "ok": validation is not None,
            "path": str(validation_path),
        }
    )
    checks.append(
        {
            "name": "assembly_observability_present",
            "type": "artifact_exists",
            "ok": observability is not None,
            "path": str(observability_path),
        }
    )
    if validation is not None:
        checks.append(
            {
                "name": "assembly_validation_passed",
                "type": "assembly_validation",
                "ok": bool(validation.get("ok")),
                "failed_checks": [
                    check.get("name") for check in validation.get("checks", []) if not check.get("ok")
                ],
            }
        )
        for key in ("mjcf", "preview_combined_iso", "preview_exploded_iso", "geometry"):
            path = (validation.get("artifacts") or {}).get(key)
            checks.append(
                {
                    "name": f"artifact:{key}",
                    "type": "artifact_exists",
                    "ok": bool(path) and Path(path).exists(),
                    "path": path,
                }
            )

    failed = [check for check in checks if not check.get("ok")]
    payload = {
        "ok": not failed,
        "stage": "assembly_review",
        "assembly": safe,
        "checks": checks,
        "summary": {"checks": len(checks), "failed": len(failed)},
        "artifacts": {"review": str(review_path), "validation": str(validation_path), "observability": str(observability_path)},
        "message": "assembly review passed" if not failed else "assembly review blocked",
    }
    write_json(review_path, payload)
    return payload


def _load_contract(project: Path, name: str) -> tuple[dict, Path]:
    contract_path = assembly_dir(project, name) / "assembly.json"
    data = read_json(contract_path, default=None)
    if data is None:
        raise AssemblyError("AssemblyMissing", f"missing assembly contract: {contract_path}")
    if data.get("schema") != ASSEMBLY_SCHEMA:
        raise AssemblyError("AssemblySchemaInvalid", f"expected schema {ASSEMBLY_SCHEMA}")
    if data.get("units", "mm") != "mm":
        raise AssemblyError("UnsupportedUnits", "assembly v1 supports millimeter units only")
    if "scale" in data:
        raise AssemblyError("ScaleNotAllowed", "assembly-level scale is not allowed")
    components = data.get("components")
    if not isinstance(components, list):
        raise AssemblyError("ComponentsInvalid", "assembly components must be a list")
    return data, contract_path


def _load_components(project: Path, contract: dict) -> dict[str, dict]:
    records: dict[str, dict] = {}
    for raw in contract.get("components", []):
        if not isinstance(raw, dict):
            raise AssemblyError("ComponentInvalid", "each component must be an object")
        cid = str(raw.get("id") or "").strip()
        model = str(raw.get("model") or "").strip()
        if not cid:
            raise AssemblyError("ComponentIdMissing", "component id is required")
        if cid in records:
            raise AssemblyError("DuplicateComponentId", f"duplicate component id: {cid}")
        if not model:
            raise AssemblyError("ComponentModelMissing", f"component {cid} is missing model")
        if "scale" in raw:
            raise AssemblyError("ScaleNotAllowed", f"component {cid} cannot define scale")
        transform = _parse_transform(raw.get("transform") or {}, cid)

        build = build_model(project, model)
        out_dir = outputs_dir(project, model)
        stl_path = out_dir / f"{model}.stl"
        step_path = out_dir / f"{model}.step"
        metadata_path = model_dir(project, model) / "metadata.json"

        local_triangles: list[Triangle] = []
        world_triangles: list[Triangle] = []
        local_report = mesh_report([])
        world_report = mesh_report([])
        if stl_path.exists():
            local_triangles = read_stl(stl_path)
            world_triangles = [_transform_triangle(tri, transform) for tri in local_triangles]
            local_report = mesh_report(local_triangles)
            world_report = mesh_report(world_triangles)
        metadata = read_json(metadata_path, default={}) or {}

        records[cid] = {
            "id": cid,
            "model": model,
            "raw": raw,
            "build": build,
            "paths": {
                "model_dir": str(model_dir(project, model)),
                "build": str(out_dir / "build.json"),
                "stl": str(stl_path),
                "step": str(step_path),
                "metadata": str(metadata_path),
            },
            "artifacts_exist": {
                "stl": stl_path.exists(),
                "step": step_path.exists(),
                "metadata": metadata_path.exists(),
            },
            "metadata": metadata,
            "transform": transform,
            "local_triangles": local_triangles,
            "world_triangles": world_triangles,
            "local_bbox": local_report.get("bbox"),
            "world_bbox": world_report.get("bbox"),
            "mesh": world_report.get("mesh"),
            "triangle_count": len(world_triangles),
        }
    return records


def _parse_transform(raw: dict, cid: str) -> Transform:
    if not isinstance(raw, dict):
        raise AssemblyError("TransformInvalid", f"component {cid} transform must be an object")
    if "scale" in raw:
        raise AssemblyError("ScaleNotAllowed", f"component {cid} transform scale is not allowed")
    allowed = {"translation", "rotation_euler_deg"}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise AssemblyError("TransformFieldInvalid", f"component {cid} transform has unsupported fields: {', '.join(unknown)}")

    translation = _vec3(raw.get("translation", [0, 0, 0]), f"{cid}.transform.translation")
    rotation_euler_deg = _vec3(raw.get("rotation_euler_deg", [0, 0, 0]), f"{cid}.transform.rotation_euler_deg")
    rotation = _rotation_matrix_xyz(rotation_euler_deg)
    matrix = [
        [rotation[0][0], rotation[0][1], rotation[0][2], translation[0]],
        [rotation[1][0], rotation[1][1], rotation[1][2], translation[1]],
        [rotation[2][0], rotation[2][1], rotation[2][2], translation[2]],
        [0.0, 0.0, 0.0, 1.0],
    ]
    return Transform(translation=translation, rotation_euler_deg=rotation_euler_deg, rotation=rotation, matrix=matrix)


def _vec3(value: Any, label: str) -> Vec3:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise AssemblyError("VectorInvalid", f"{label} must be a 3-item number array")
    try:
        return (float(value[0]), float(value[1]), float(value[2]))
    except (TypeError, ValueError) as exc:
        raise AssemblyError("VectorInvalid", f"{label} must contain numbers") from exc


def _rotation_matrix_xyz(euler_deg: Vec3) -> tuple[Vec3, Vec3, Vec3]:
    rx, ry, rz = [math.radians(v) for v in euler_deg]
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    mx: tuple[Vec3, Vec3, Vec3] = ((1.0, 0.0, 0.0), (0.0, cx, -sx), (0.0, sx, cx))
    my: tuple[Vec3, Vec3, Vec3] = ((cy, 0.0, sy), (0.0, 1.0, 0.0), (-sy, 0.0, cy))
    mz: tuple[Vec3, Vec3, Vec3] = ((cz, -sz, 0.0), (sz, cz, 0.0), (0.0, 0.0, 1.0))
    return _matmul3(_matmul3(mz, my), mx)


def _matmul3(a: tuple[Vec3, Vec3, Vec3], b: tuple[Vec3, Vec3, Vec3]) -> tuple[Vec3, Vec3, Vec3]:
    rows = []
    for i in range(3):
        rows.append(
            (
                a[i][0] * b[0][0] + a[i][1] * b[1][0] + a[i][2] * b[2][0],
                a[i][0] * b[0][1] + a[i][1] * b[1][1] + a[i][2] * b[2][1],
                a[i][0] * b[0][2] + a[i][1] * b[1][2] + a[i][2] * b[2][2],
            )
        )
    return (rows[0], rows[1], rows[2])


def _transform_point(point: Vec3, transform: Transform) -> Vec3:
    return _transform_point_matrix(point, transform.matrix)


def _transform_vector(vector: Vec3, transform: Transform) -> Vec3:
    return normalize(
        (
            transform.rotation[0][0] * vector[0] + transform.rotation[0][1] * vector[1] + transform.rotation[0][2] * vector[2],
            transform.rotation[1][0] * vector[0] + transform.rotation[1][1] * vector[1] + transform.rotation[1][2] * vector[2],
            transform.rotation[2][0] * vector[0] + transform.rotation[2][1] * vector[1] + transform.rotation[2][2] * vector[2],
        )
    )


def _transform_point_matrix(point: Vec3, matrix: list[list[float]]) -> Vec3:
    return (
        matrix[0][0] * point[0] + matrix[0][1] * point[1] + matrix[0][2] * point[2] + matrix[0][3],
        matrix[1][0] * point[0] + matrix[1][1] * point[1] + matrix[1][2] * point[2] + matrix[1][3],
        matrix[2][0] * point[0] + matrix[2][1] * point[1] + matrix[2][2] * point[2] + matrix[2][3],
    )


def _transform_triangle(tri: Triangle, transform: Transform) -> Triangle:
    return (_transform_point(tri[0], transform), _transform_point(tri[1], transform), _transform_point(tri[2], transform))


def _translate_triangle(tri: Triangle, offset: Vec3) -> Triangle:
    return (_add(tri[0], offset), _add(tri[1], offset), _add(tri[2], offset))


def _add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(v: Vec3, scalar: float) -> Vec3:
    return (v[0] * scalar, v[1] * scalar, v[2] * scalar)


def _public_component_record(record: dict) -> dict:
    transform: Transform = record["transform"]
    return {
        "id": record["id"],
        "model": record["model"],
        "paths": record["paths"],
        "build": {
            "ok": bool(record.get("build", {}).get("ok")),
            "sourceHash": record.get("build", {}).get("sourceHash"),
            "skipped": bool(record.get("build", {}).get("skipped")),
        },
        "artifacts_exist": record["artifacts_exist"],
        "transform": {
            "translation": _round_vec(transform.translation),
            "rotation_euler_deg": _round_vec(transform.rotation_euler_deg),
            "matrix": _round_matrix(transform.matrix),
        },
        "local_bbox": record["local_bbox"],
        "world_bbox": record["world_bbox"],
        "mesh": record["mesh"],
        "triangle_count": record["triangle_count"],
    }


def _collect_references(contract: dict) -> list[str]:
    refs: list[str] = []
    for mate in contract.get("mates", []) or []:
        if isinstance(mate, dict):
            for key in ("a", "b"):
                _append_ref(refs, mate.get(key))
    for check in contract.get("checks", []) or []:
        if isinstance(check, dict):
            for key in ("ref", "path", "a", "b", "inner", "outer"):
                _append_ref(refs, check.get(key))
    return sorted(set(refs))


def _append_ref(refs: list[str], value: Any) -> None:
    if isinstance(value, str) and "." in value:
        refs.append(value)


def _resolve_references(refs: list[str], components: dict[str, dict]) -> dict[str, dict]:
    resolved: dict[str, dict] = {}
    for ref in refs:
        parts = ref.split(".")
        cid = parts[0]
        record = components.get(cid)
        if record is None:
            resolved[ref] = {
                "ok": False,
                "ref": ref,
                "component": cid,
                "error": {"type": "ComponentMissing", "message": f"unknown component: {cid}"},
            }
            continue
        local = _dig(record.get("metadata") or {}, parts[1:])
        if local is None:
            resolved[ref] = {
                "ok": False,
                "ref": ref,
                "component": cid,
                "path": ".".join(parts[1:]),
                "error": {"type": "ReferenceMissing", "message": f"metadata reference not found: {ref}"},
            }
            continue
        resolved[ref] = {
            "ok": True,
            "ref": ref,
            "component": cid,
            "path": ".".join(parts[1:]),
            "local": local,
            "world": _transform_descriptor(local, record["transform"]),
        }
    return resolved


def _dig(value: Any, parts: list[str]) -> Any:
    current = value
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _transform_descriptor(value: Any, transform: Transform) -> Any:
    if isinstance(value, list):
        return [_transform_descriptor(item, transform) for item in value]
    if not isinstance(value, dict):
        return value
    if _is_axis_descriptor(value):
        point = _vec3(value.get("point", [0, 0, 0]), "axis.point")
        direction = _vec3(value.get("direction", [0, 0, 1]), "axis.direction")
        return {
            **value,
            "point": list(value.get("point", [0, 0, 0])),
            "direction": list(value.get("direction", [0, 0, 1])),
            "world_point": _round_vec(_transform_point(point, transform)),
            "world_direction": _round_vec(_transform_vector(direction, transform)),
        }
    if _is_cylinder_descriptor(value):
        endpoints = _cylinder_endpoints(value)
        world_a = _transform_point(endpoints[0], transform)
        world_b = _transform_point(endpoints[1], transform)
        return {
            **value,
            "world_axis_point": _round_vec(world_a),
            "world_axis_end": _round_vec(world_b),
            "world_axis_direction": _round_vec(normalize(sub(world_b, world_a))),
            "radius_mm": _descriptor_radius(value),
        }
    transformed = {}
    for key, item in value.items():
        transformed[key] = _transform_descriptor(item, transform)
    return transformed


def _is_axis_descriptor(value: Any) -> bool:
    return isinstance(value, dict) and "point" in value and "direction" in value


def _is_cylinder_descriptor(value: Any) -> bool:
    return isinstance(value, dict) and value.get("type") == "cylinder"


def _descriptor_radius(desc: dict) -> float | None:
    for key in ("radius_mm", "radius"):
        if key in desc:
            return float(desc[key])
    if "diameter_mm" in desc:
        return float(desc["diameter_mm"]) / 2.0
    if "diameter" in desc:
        return float(desc["diameter"]) / 2.0
    return None


def _cylinder_endpoints(desc: dict) -> tuple[Vec3, Vec3]:
    axis = desc.get("axis", "z")
    z_range = desc.get("z_range") or desc.get("range") or [0.0, 0.0]
    if not isinstance(z_range, (list, tuple)) or len(z_range) != 2:
        raise AssemblyError("CylinderDescriptorInvalid", "cylinder z_range must contain two values")
    start = float(z_range[0])
    end = float(z_range[1])
    center = desc.get("center", [0.0, 0.0])
    if axis == "z":
        if len(center) == 2:
            return ((float(center[0]), float(center[1]), start), (float(center[0]), float(center[1]), end))
        if len(center) == 3:
            return ((float(center[0]), float(center[1]), start), (float(center[0]), float(center[1]), end))
    if axis == "x" and len(center) >= 2:
        y, z = float(center[0]), float(center[1])
        return ((start, y, z), (end, y, z))
    if axis == "y" and len(center) >= 2:
        x, z = float(center[0]), float(center[1])
        return ((x, start, z), (x, end, z))
    raise AssemblyError("CylinderDescriptorInvalid", f"unsupported cylinder axis: {axis}")


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


def _evaluate_mates(contract: dict, resolved_refs: dict[str, dict]) -> list[dict]:
    results = []
    for index, mate in enumerate(contract.get("mates", []) or []):
        if not isinstance(mate, dict):
            continue
        mtype = mate.get("type")
        name = mate.get("id") or f"mate_{index}"
        if mtype in ("coaxial", "mate_coaxial"):
            results.append(_eval_mate_coaxial(name, mate, resolved_refs))
        elif mtype in ("axis_aligned", "mate_axis_aligned"):
            results.append(_eval_mate_axis_aligned(name, mate, resolved_refs))
        elif mtype in ("coincident", "mate_coincident"):
            results.append(_eval_mate_coincident(name, mate, resolved_refs))
        elif mtype == "axial_engagement":
            results.append(_eval_axial_engagement(name, mate, resolved_refs))
        else:
            results.append(
                {
                    "name": name,
                    "type": mtype,
                    "ok": False,
                    "measurable": False,
                    "error": {"type": "UnsupportedMateType", "message": f"unsupported mate type: {mtype}"},
                }
            )
    return results


def _eval_mate_coaxial(name: str, mate: dict, refs: dict[str, dict]) -> dict:
    max_angle = _required_float(mate, "max_axis_angle_deg", name)
    max_offset = _required_float(mate, "max_radial_offset_mm", name)
    axis_a = _axis_from_ref(mate.get("a"), refs)
    axis_b = _axis_from_ref(mate.get("b"), refs)
    if axis_a is None or axis_b is None:
        return _unmeasurable_mate(name, "coaxial", mate, "AxisMissing", "both refs must resolve to axis-like descriptors")
    angle = _angle_deg(axis_a[1], axis_b[1])
    radial_offset = _point_axis_distance(axis_b[0], axis_a[0], axis_a[1])
    ok = max_angle is not None and max_offset is not None and angle <= max_angle and radial_offset <= max_offset
    return {
        "name": name,
        "type": "mate_coaxial",
        "ok": ok,
        "measurable": True,
        "components": _components_from_refs([mate.get("a"), mate.get("b")]),
        "angle_deg": angle,
        "radial_offset_mm": radial_offset,
        "max_axis_angle_deg": max_angle,
        "max_radial_offset_mm": max_offset,
    }


def _eval_mate_axis_aligned(name: str, mate: dict, refs: dict[str, dict]) -> dict:
    max_angle = _required_float(mate, "max_axis_angle_deg", name)
    axis_a = _axis_from_ref(mate.get("a"), refs)
    axis_b = _axis_from_ref(mate.get("b"), refs)
    if axis_a is None or axis_b is None:
        return _unmeasurable_mate(name, "axis_aligned", mate, "AxisMissing", "both refs must resolve to axis-like descriptors")
    angle = _angle_deg(axis_a[1], axis_b[1])
    return {
        "name": name,
        "type": "mate_axis_aligned",
        "ok": max_angle is not None and angle <= max_angle,
        "measurable": True,
        "components": _components_from_refs([mate.get("a"), mate.get("b")]),
        "angle_deg": angle,
        "max_axis_angle_deg": max_angle,
    }


def _eval_mate_coincident(name: str, mate: dict, refs: dict[str, dict]) -> dict:
    max_distance = _required_float(mate, "max_distance_mm", name)
    point_a = _point_from_ref(mate.get("a"), refs)
    point_b = _point_from_ref(mate.get("b"), refs)
    if point_a is None or point_b is None:
        return _unmeasurable_mate(name, "coincident", mate, "PointMissing", "both refs must resolve to point-like descriptors")
    distance = length(sub(point_b, point_a))
    return {
        "name": name,
        "type": "mate_coincident",
        "ok": max_distance is not None and distance <= max_distance,
        "measurable": True,
        "components": _components_from_refs([mate.get("a"), mate.get("b")]),
        "distance_mm": distance,
        "max_distance_mm": max_distance,
    }


def _eval_axial_engagement(name: str, mate: dict, refs: dict[str, dict]) -> dict:
    min_mm = _required_float(mate, "min_mm", name)
    interval_a = _axis_interval_from_ref(mate.get("a"), refs)
    interval_b = _axis_interval_from_ref(mate.get("b"), refs)
    if interval_a is None or interval_b is None:
        return _unmeasurable_mate(name, "axial_engagement", mate, "AxisIntervalMissing", "both refs must resolve to cylindrical or axis interval descriptors")
    axis = interval_a["axis"]
    projections_a = [dot(point, axis) for point in interval_a["points"]]
    projections_b = [dot(point, axis) for point in interval_b["points"]]
    a_min, a_max = min(projections_a), max(projections_a)
    b_min, b_max = min(projections_b), max(projections_b)
    overlap = max(0.0, min(a_max, b_max) - max(a_min, b_min))
    return {
        "name": name,
        "type": "axial_engagement",
        "ok": min_mm is not None and overlap >= min_mm,
        "measurable": True,
        "components": _components_from_refs([mate.get("a"), mate.get("b")]),
        "actual_mm": overlap,
        "min_mm": min_mm,
        "intervals": {
            "a": [a_min, a_max],
            "b": [b_min, b_max],
        },
    }


def _required_float(payload: dict, key: str, name: str) -> float | None:
    if key not in payload:
        return None
    try:
        return float(payload[key])
    except (TypeError, ValueError) as exc:
        raise AssemblyError("ToleranceInvalid", f"{name}.{key} must be numeric") from exc


def _unmeasurable_mate(name: str, mtype: str, mate: dict, error_type: str, message: str) -> dict:
    return {
        "name": name,
        "type": f"mate_{mtype}",
        "ok": False,
        "measurable": False,
        "components": _components_from_refs([mate.get("a"), mate.get("b")]),
        "error": {"type": error_type, "message": message},
    }


def _axis_from_ref(ref: Any, refs: dict[str, dict]) -> tuple[Vec3, Vec3] | None:
    if not isinstance(ref, str):
        return None
    resolved = refs.get(ref)
    if not resolved or not resolved.get("ok"):
        return None
    return _axis_from_descriptor(resolved.get("world"))


def _axis_from_descriptor(desc: Any) -> tuple[Vec3, Vec3] | None:
    if not isinstance(desc, dict):
        return None
    if "world_point" in desc and "world_direction" in desc:
        return (_vec3(desc["world_point"], "axis.world_point"), normalize(_vec3(desc["world_direction"], "axis.world_direction")))
    if "world_axis_point" in desc and "world_axis_direction" in desc:
        return (
            _vec3(desc["world_axis_point"], "cylinder.world_axis_point"),
            normalize(_vec3(desc["world_axis_direction"], "cylinder.world_axis_direction")),
        )
    if "axis" in desc:
        return _axis_from_descriptor(desc["axis"])
    for key in ("outer_cylinder", "inner_cylinder", "cylinder"):
        if key in desc:
            axis = _axis_from_descriptor(desc[key])
            if axis is not None:
                return axis
    return None


def _point_from_ref(ref: Any, refs: dict[str, dict]) -> Vec3 | None:
    if not isinstance(ref, str):
        return None
    resolved = refs.get(ref)
    if not resolved or not resolved.get("ok"):
        return None
    return _point_from_descriptor(resolved.get("world"))


def _point_from_descriptor(desc: Any) -> Vec3 | None:
    if not isinstance(desc, dict):
        return None
    if "world_point" in desc:
        return _vec3(desc["world_point"], "point.world_point")
    if "world_axis_point" in desc:
        return _vec3(desc["world_axis_point"], "cylinder.world_axis_point")
    if "axis" in desc:
        point = _point_from_descriptor(desc["axis"])
        if point is not None:
            return point
    for key in ("outer_cylinder", "inner_cylinder", "cylinder"):
        if key in desc:
            point = _point_from_descriptor(desc[key])
            if point is not None:
                return point
    return None


def _axis_interval_from_ref(ref: Any, refs: dict[str, dict]) -> dict | None:
    if not isinstance(ref, str):
        return None
    resolved = refs.get(ref)
    if not resolved or not resolved.get("ok"):
        return None
    return _axis_interval_from_descriptor(resolved.get("world"))


def _axis_interval_from_descriptor(desc: Any) -> dict | None:
    if not isinstance(desc, dict):
        return None
    if "world_axis_point" in desc and "world_axis_end" in desc:
        a = _vec3(desc["world_axis_point"], "cylinder.world_axis_point")
        b = _vec3(desc["world_axis_end"], "cylinder.world_axis_end")
        return {"axis": normalize(sub(b, a)), "points": [a, b]}
    for key in ("outer_cylinder", "inner_cylinder", "cylinder"):
        if key in desc:
            interval = _axis_interval_from_descriptor(desc[key])
            if interval is not None:
                return interval
    return None


def _angle_deg(a: Vec3, b: Vec3) -> float:
    value = max(-1.0, min(1.0, abs(dot(normalize(a), normalize(b)))))
    return math.degrees(math.acos(value))


def _point_axis_distance(point: Vec3, axis_point: Vec3, axis_dir: Vec3) -> float:
    return length(cross(sub(point, axis_point), normalize(axis_dir)))


def _measure_pairwise(components: dict[str, dict]) -> list[dict]:
    rows = []
    for a_id, b_id in itertools.combinations(sorted(components), 2):
        bbox_a = components[a_id].get("world_bbox")
        bbox_b = components[b_id].get("world_bbox")
        rows.append(
            {
                "components": [a_id, b_id],
                "bbox_overlap": _bbox_overlap(bbox_a, bbox_b),
                "aabb_clearance_mm": _bbox_clearance(bbox_a, bbox_b),
            }
        )
    return rows


def _bbox_overlap(a: dict | None, b: dict | None) -> bool:
    if not a or not b:
        return False
    return all(a["min"][i] <= b["max"][i] + EPS and b["min"][i] <= a["max"][i] + EPS for i in range(3))


def _bbox_clearance(a: dict | None, b: dict | None) -> float | None:
    if not a or not b:
        return None
    distances = []
    for i in range(3):
        if a["max"][i] < b["min"][i]:
            distances.append(b["min"][i] - a["max"][i])
        elif b["max"][i] < a["min"][i]:
            distances.append(a["min"][i] - b["max"][i])
        else:
            distances.append(0.0)
    return math.sqrt(sum(distance * distance for distance in distances))


def _global_bbox(bboxes: list[dict | None]) -> dict | None:
    valid = [bbox for bbox in bboxes if bbox]
    if not valid:
        return None
    min_v = [min(bbox["min"][i] for bbox in valid) for i in range(3)]
    max_v = [max(bbox["max"][i] for bbox in valid) for i in range(3)]
    return {
        "min": min_v,
        "max": max_v,
        "size": [max_v[i] - min_v[i] for i in range(3)],
        "center": [(max_v[i] + min_v[i]) / 2.0 for i in range(3)],
    }


def _fresh_component_checks(geometry: dict) -> list[dict]:
    checks = []
    for cid, component in (geometry.get("components") or {}).items():
        build_ok = bool(component.get("build", {}).get("ok"))
        artifacts = component.get("artifacts_exist") or {}
        ok = build_ok and all(artifacts.get(key) for key in ("stl", "step", "metadata"))
        checks.append(
            {
                "name": f"fresh_component:{cid}",
                "type": "component_exists",
                "ok": ok,
                "component": cid,
                "model": component.get("model"),
                "build_ok": build_ok,
                "artifacts_exist": artifacts,
                "paths": component.get("paths"),
            }
        )
    return checks


def _mate_checks(geometry: dict) -> list[dict]:
    checks = []
    for mate in geometry.get("mate_residuals", []) or []:
        checks.append({**mate, "type": mate.get("type") or "mate", "name": mate.get("name")})
    return checks


def _evaluate_user_checks(contract: dict, geometry: dict) -> list[dict]:
    checks = []
    for index, check in enumerate(contract.get("checks", []) or []):
        if not isinstance(check, dict):
            continue
        ctype = check.get("type")
        name = check.get("id") or f"check_{index}"
        if ctype == "radial_clearance":
            checks.append(_eval_radial_clearance(name, check, geometry))
        elif ctype == "interference_free":
            checks.append(_eval_interference_free(name, check, geometry))
        elif ctype == "inter_model_min_clearance":
            checks.append(_eval_inter_model_min_clearance(name, check, geometry))
        elif ctype == "assembly_bbox_size":
            checks.append(_eval_assembly_bbox_size(name, check, geometry))
        elif ctype in ("anchor_exists", "interface_exists"):
            checks.append(_eval_reference_exists(name, ctype, check, geometry))
        elif ctype == "component_exists":
            checks.append(_eval_component_exists(name, check, geometry))
        else:
            checks.append(
                {
                    "name": name,
                    "type": ctype,
                    "ok": False,
                    "error": {"type": "UnsupportedCheckType", "message": f"unsupported assembly check type: {ctype}"},
                }
            )
    return checks


def _eval_radial_clearance(name: str, check: dict, geometry: dict) -> dict:
    refs = geometry.get("references") or {}
    inner_ref = check.get("inner")
    outer_ref = check.get("outer")
    inner_radius = _measured_radius_for_ref(inner_ref, "inner", geometry)
    outer_radius = _measured_radius_for_ref(outer_ref, "outer", geometry)
    min_mm = _required_float(check, "min_mm", name)
    max_mm = _required_float(check, "max_mm", name)
    if inner_radius is None or outer_radius is None:
        return {
            "name": name,
            "type": "radial_clearance",
            "ok": False,
            "components": _components_from_refs([inner_ref, outer_ref]),
            "error": {"type": "RadiusMissing", "message": "inner and outer references must resolve to measured cylinder radii"},
        }
    actual = inner_radius - outer_radius
    return {
        "name": name,
        "type": "radial_clearance",
        "ok": min_mm is not None and max_mm is not None and min_mm <= actual <= max_mm,
        "components": _components_from_refs([inner_ref, outer_ref]),
        "actual_mm": actual,
        "min_mm": min_mm,
        "max_mm": max_mm,
        "evidence": {
            "inner": inner_ref,
            "outer": outer_ref,
            "inner_reference_ok": bool(refs.get(inner_ref, {}).get("ok")) if isinstance(inner_ref, str) else False,
            "outer_reference_ok": bool(refs.get(outer_ref, {}).get("ok")) if isinstance(outer_ref, str) else False,
            "inner_radius_mm": inner_radius,
            "outer_radius_mm": outer_radius,
        },
    }


def _measured_radius_for_ref(ref: Any, surface: str, geometry: dict) -> float | None:
    if not isinstance(ref, str):
        return None
    for check in geometry.get("metadata_geometry_checks", []) or []:
        if check.get("ref") == ref and check.get("measured_radius_mm") is not None:
            return float(check["measured_radius_mm"])
    resolved = (geometry.get("references") or {}).get(ref)
    if not resolved or not resolved.get("ok"):
        return None
    return _radius_from_descriptor(resolved.get("local"), surface)


def _radius_from_descriptor(desc: Any, surface: str) -> float | None:
    if _is_cylinder_descriptor(desc):
        return _descriptor_radius(desc)
    if isinstance(desc, dict):
        preferred = "inner_cylinder" if surface == "inner" else "outer_cylinder"
        if preferred in desc:
            return _radius_from_descriptor(desc[preferred], surface)
        for item in desc.values():
            result = _radius_from_descriptor(item, surface)
            if result is not None:
                return result
    return None


def _eval_interference_free(name: str, check: dict, geometry: dict) -> dict:
    pair = _pair_key(check.get("components") or [])
    row = _pair_row(geometry, pair)
    if row is None:
        return {
            "name": name,
            "type": "interference_free",
            "ok": False,
            "components": list(pair),
            "error": {"type": "PairMissing", "message": "component pair not found"},
        }
    overlap = bool(row.get("bbox_overlap"))
    return {
        "name": name,
        "type": "interference_free",
        "ok": not overlap,
        "components": list(pair),
        "method": "aabb_conservative",
        "bbox_overlap": overlap,
        "aabb_clearance_mm": row.get("aabb_clearance_mm"),
        "error": {"type": "AabbOverlapRequiresNarrowPhase", "message": "AABB overlap is treated as a failure in MVP"} if overlap else None,
    }


def _eval_inter_model_min_clearance(name: str, check: dict, geometry: dict) -> dict:
    pair = _pair_key(check.get("components") or [])
    row = _pair_row(geometry, pair)
    min_mm = _required_float(check, "min_mm", name)
    if row is None:
        return {
            "name": name,
            "type": "inter_model_min_clearance",
            "ok": False,
            "components": list(pair),
            "error": {"type": "PairMissing", "message": "component pair not found"},
        }
    actual = row.get("aabb_clearance_mm")
    return {
        "name": name,
        "type": "inter_model_min_clearance",
        "ok": actual is not None and min_mm is not None and actual >= min_mm,
        "components": list(pair),
        "actual_mm": actual,
        "min_mm": min_mm,
        "method": "aabb",
    }


def _eval_assembly_bbox_size(name: str, check: dict, geometry: dict) -> dict:
    expected = check.get("expected") or check.get("size")
    if not isinstance(expected, (list, tuple)) or len(expected) != 3:
        return {
            "name": name,
            "type": "assembly_bbox_size",
            "ok": False,
            "error": {"type": "ExpectedSizeMissing", "message": "expected or size must be a 3-item array"},
        }
    tol = float(check.get("tolerance_mm", 0.1))
    bbox = (geometry.get("assembly_geometry") or {}).get("bbox")
    actual = bbox.get("size") if bbox else None
    ok = actual is not None and all(abs(float(actual[i]) - float(expected[i])) <= tol for i in range(3))
    return {
        "name": name,
        "type": "assembly_bbox_size",
        "ok": ok,
        "actual": actual,
        "expected": [float(value) for value in expected],
        "tolerance_mm": tol,
    }


def _eval_reference_exists(name: str, ctype: str, check: dict, geometry: dict) -> dict:
    ref = check.get("ref") or check.get("path")
    resolved = (geometry.get("references") or {}).get(ref)
    return {
        "name": name,
        "type": ctype,
        "ok": bool(resolved and resolved.get("ok")),
        "ref": ref,
        "error": None if resolved and resolved.get("ok") else (resolved or {}).get("error", {"type": "ReferenceMissing"}),
    }


def _eval_component_exists(name: str, check: dict, geometry: dict) -> dict:
    cid = check.get("component") or check.get("id")
    component = (geometry.get("components") or {}).get(cid)
    return {
        "name": name,
        "type": "component_exists",
        "ok": bool(component),
        "component": cid,
    }


def _fit_coverage_checks(contract: dict, geometry: dict) -> list[dict]:
    checks = []
    radial_pairs = {
        frozenset(_components_from_refs([check.get("inner"), check.get("outer")]))
        for check in contract.get("checks", []) or []
        if isinstance(check, dict) and check.get("type") == "radial_clearance"
    }
    for mate in contract.get("mates", []) or []:
        if not isinstance(mate, dict) or mate.get("type") != "axial_engagement":
            continue
        pair = frozenset(_components_from_refs([mate.get("a"), mate.get("b")]))
        checks.append(
            {
                "name": f"fit_coverage:{mate.get('id') or 'axial_engagement'}",
                "type": "fit_coverage",
                "ok": pair in radial_pairs,
                "components": sorted(pair),
                "requires": ["radial_clearance", "axial_engagement"],
                "has_radial_clearance": pair in radial_pairs,
            }
        )
    return checks


def _component_pair_classification_checks(contract: dict, geometry: dict) -> list[dict]:
    covered = set()
    for check in contract.get("checks", []) or []:
        if isinstance(check, dict) and check.get("type") in ("interference_free", "inter_model_min_clearance"):
            covered.add(_pair_key(check.get("components") or []))
    ignored = {
        _pair_key(item.get("components") or []): item
        for item in contract.get("ignore_pairs", []) or []
        if isinstance(item, dict)
    }
    checks = []
    for row in geometry.get("pairwise", []) or []:
        pair = _pair_key(row.get("components") or [])
        ignore = ignored.get(pair)
        ok = pair in covered or (ignore is not None and bool(str(ignore.get("reason") or "").strip()))
        checks.append(
            {
                "name": f"component_pair_classified:{'+'.join(pair)}",
                "type": "component_pair_classified",
                "ok": ok,
                "components": list(pair),
                "coverage": "check" if pair in covered else ("ignore" if ignore else None),
                "reason": ignore.get("reason") if ignore else None,
            }
        )
    return checks


def _pair_key(value: Any) -> tuple[str, str]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return ("", "")
    return tuple(sorted((str(value[0]), str(value[1]))))  # type: ignore[return-value]


def _pair_row(geometry: dict, pair: tuple[str, str]) -> dict | None:
    for row in geometry.get("pairwise", []) or []:
        if _pair_key(row.get("components") or []) == pair:
            return row
    return None


def _components_from_refs(refs: list[Any]) -> list[str]:
    components = []
    for ref in refs:
        if isinstance(ref, str) and "." in ref:
            components.append(ref.split(".", 1)[0])
    return sorted(set(components))


def _render_assembly_previews(project: Path, name: str, geometry: dict) -> dict:
    out_dir = assembly_outputs_dir(project, name)
    try:
        combined = _assembly_triangles_from_geometry(geometry)
        combined_path = out_dir / "preview.combined.iso.svg"
        combined_path.write_text(triangles_to_svg(combined, title=f"{name} combined iso", view="iso"), encoding="utf-8")

        exploded = _exploded_triangles_from_geometry(geometry)
        exploded_path = out_dir / "preview.exploded.iso.svg"
        exploded_path.write_text(triangles_to_svg(exploded, title=f"{name} exploded iso", view="iso"), encoding="utf-8")

        return {
            "ok": True,
            "stage": "assembly_render",
            "assembly": name,
            "artifacts": {
                "preview_combined_iso": str(combined_path),
                "preview_exploded_iso": str(exploded_path),
            },
        }
    except Exception as exc:
        return {
            "ok": False,
            "stage": "assembly_render",
            "assembly": name,
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }


def _assembly_triangles_from_geometry(geometry: dict) -> list[Triangle]:
    triangles: list[Triangle] = []
    for component in (geometry.get("components") or {}).values():
        stl_path = Path(component["paths"]["stl"])
        matrix = component["transform"]["matrix"]
        for tri in read_stl(stl_path):
            triangles.append(tuple(_transform_point_matrix(point, matrix) for point in tri))  # type: ignore[arg-type]
    return triangles


def _exploded_triangles_from_geometry(geometry: dict) -> list[Triangle]:
    bbox = (geometry.get("assembly_geometry") or {}).get("bbox") or {}
    center = _vec3(bbox.get("center", [0, 0, 0]), "assembly.bbox.center")
    size = bbox.get("size") or [0, 0, 0]
    offset_distance = max(float(size[0]), float(size[1]), float(size[2]), 1.0) * 0.35 + 10.0
    triangles: list[Triangle] = []
    components = list((geometry.get("components") or {}).values())
    for index, component in enumerate(components):
        comp_bbox = component.get("world_bbox") or {}
        comp_center = _vec3(comp_bbox.get("center", [0, 0, 0]), "component.bbox.center")
        direction = normalize(sub(comp_center, center))
        if length(direction) <= EPS:
            angle = 2.0 * math.pi * index / max(len(components), 1)
            direction = (math.cos(angle), math.sin(angle), 0.2)
        offset = _mul(normalize(direction), offset_distance)
        stl_path = Path(component["paths"]["stl"])
        matrix = component["transform"]["matrix"]
        for tri in read_stl(stl_path):
            world_tri = tuple(_transform_point_matrix(point, matrix) for point in tri)  # type: ignore[arg-type]
            triangles.append(_translate_triangle(world_tri, offset))
    return triangles


def _export_mjcf(project: Path, name: str, contract: dict, geometry: dict) -> dict:
    out_dir = assembly_outputs_dir(project, name)
    out_path = out_dir / f"{name}.mjcf.xml"
    try:
        root = ET.Element("mujoco", {"model": name})
        ET.SubElement(root, "compiler", {"angle": "degree", "coordinate": "local"})
        asset = ET.SubElement(root, "asset")
        worldbody = ET.SubElement(root, "worldbody")
        site_specs: dict[str, dict] = {}

        for cid, component in (geometry.get("components") or {}).items():
            mesh_name = f"{_safe_xml_name(cid)}_mesh"
            mesh_file = os.path.relpath(component["paths"]["stl"], start=out_dir)
            ET.SubElement(asset, "mesh", {"name": mesh_name, "file": mesh_file})
            transform = component["transform"]
            body = ET.SubElement(
                worldbody,
                "body",
                {
                    "name": cid,
                    "pos": _mjcf_vec(transform["translation"]),
                    "euler": _mjcf_vec(transform["rotation_euler_deg"]),
                },
            )
            ET.SubElement(body, "geom", {"name": f"{_safe_xml_name(cid)}_geom", "type": "mesh", "mesh": mesh_name})
            for ref, resolved in sorted((geometry.get("references") or {}).items()):
                if resolved.get("component") != cid or not resolved.get("ok"):
                    continue
                site = _local_site_from_descriptor(resolved.get("local"))
                if site is None:
                    continue
                site_name = _safe_xml_name(ref.replace(".", "_"))
                ET.SubElement(body, "site", {"name": site_name, "pos": _mjcf_vec(site), "size": "0.5"})
                site_specs[site_name] = {"component": cid, "ref": ref, "pos": _round_vec(site)}

        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        tree.write(out_path, encoding="utf-8", xml_declaration=True)
        return {
            "ok": True,
            "stage": "assembly_export_mjcf",
            "assembly": name,
            "site_specs": site_specs,
            "artifacts": {"mjcf": str(out_path)},
        }
    except Exception as exc:
        return {
            "ok": False,
            "stage": "assembly_export_mjcf",
            "assembly": name,
            "error": {"type": type(exc).__name__, "message": str(exc)},
            "artifacts": {"mjcf": str(out_path)},
        }


def _local_site_from_descriptor(desc: Any) -> Vec3 | None:
    if not isinstance(desc, dict):
        return None
    if _is_axis_descriptor(desc):
        return _vec3(desc.get("point", [0, 0, 0]), "site.axis.point")
    if _is_cylinder_descriptor(desc):
        a, b = _cylinder_endpoints(desc)
        return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0, (a[2] + b[2]) / 2.0)
    if "point" in desc and isinstance(desc.get("point"), (list, tuple)) and len(desc["point"]) == 3:
        return _vec3(desc["point"], "site.point")
    if "axis" in desc:
        site = _local_site_from_descriptor(desc["axis"])
        if site is not None:
            return site
    for key in ("outer_cylinder", "inner_cylinder", "cylinder"):
        if key in desc:
            site = _local_site_from_descriptor(desc[key])
            if site is not None:
                return site
    return None


def _mjcf_consistency_check(mjcf_payload: dict, geometry: dict) -> dict:
    path = (mjcf_payload.get("artifacts") or {}).get("mjcf")
    if not mjcf_payload.get("ok") or not path:
        return {
            "name": "mjcf_consistency",
            "type": "mjcf_consistency",
            "ok": False,
            "error": mjcf_payload.get("error") or {"type": "MJCFMissing"},
        }
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        asset_mesh = {mesh.attrib.get("name"): mesh.attrib.get("file") for mesh in root.findall("./asset/mesh")}
        bodies = {body.attrib.get("name"): body for body in root.findall("./worldbody/body")}
        errors = []
        out_dir = Path(path).parent
        for cid, component in (geometry.get("components") or {}).items():
            body = bodies.get(cid)
            if body is None:
                errors.append(f"missing body {cid}")
                continue
            if not _vectors_close(_parse_mjcf_vec(body.attrib.get("pos", "")), component["transform"]["translation"]):
                errors.append(f"body {cid} pos mismatch")
            if not _vectors_close(_parse_mjcf_vec(body.attrib.get("euler", "")), component["transform"]["rotation_euler_deg"]):
                errors.append(f"body {cid} euler mismatch")
            geom = body.find("geom")
            mesh_name = geom.attrib.get("mesh") if geom is not None else None
            mesh_file = asset_mesh.get(mesh_name)
            expected = os.path.relpath(component["paths"]["stl"], start=out_dir)
            if mesh_file != expected:
                errors.append(f"body {cid} mesh path mismatch")
            for site in body.findall("site"):
                site_name = site.attrib.get("name") or ""
                spec = (mjcf_payload.get("site_specs") or {}).get(site_name)
                if spec and not _vectors_close(_parse_mjcf_vec(site.attrib.get("pos", "")), spec["pos"]):
                    errors.append(f"site {site_name} pos mismatch")
        return {
            "name": "mjcf_consistency",
            "type": "mjcf_consistency",
            "ok": not errors,
            "artifact": path,
            "errors": errors,
        }
    except Exception as exc:
        return {
            "name": "mjcf_consistency",
            "type": "mjcf_consistency",
            "ok": False,
            "artifact": path,
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }


def _transform_consistency_check(geometry: dict, mjcf_payload: dict) -> dict:
    ok = bool(mjcf_payload.get("ok"))
    return {
        "name": "transform_consistency",
        "type": "transform_consistency",
        "ok": ok,
        "source": "assembly_geometry.transform.matrix",
        "uses": ["stl_world_bbox", "svg_previews", "mjcf_body_pose"],
    }


def _write_observability(path: Path, name: str, geometry: dict, validation: dict) -> None:
    failed_checks = [check for check in validation.get("checks", []) if not check.get("ok")]
    payload = {
        "ok": bool(validation.get("ok")),
        "schema": OBSERVABILITY_SCHEMA,
        "stage": "assembly_observability",
        "assembly": name,
        "geometry": geometry.get("assembly_geometry"),
        "components": geometry.get("components"),
        "references": geometry.get("references"),
        "mate_residuals": geometry.get("mate_residuals"),
        "pairwise": geometry.get("pairwise"),
        "checks": {
            "total": len(validation.get("checks", [])),
            "failed": [
                {
                    "name": check.get("name"),
                    "type": check.get("type"),
                    "error": check.get("error"),
                    "components": check.get("components"),
                }
                for check in failed_checks
            ],
        },
        "artifacts": validation.get("artifacts"),
    }
    write_json(path, payload)


def _mjcf_vec(values: Any) -> str:
    return " ".join(f"{float(value):.9g}" for value in values)


def _parse_mjcf_vec(value: str) -> list[float]:
    return [float(part) for part in value.split()]


def _safe_xml_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
    if not cleaned or not (cleaned[0].isalpha() or cleaned[0] == "_"):
        cleaned = f"n_{cleaned}"
    return cleaned


def _vectors_close(a: list[float], b: list[float], tol: float = 1e-6) -> bool:
    return len(a) == len(b) and all(abs(float(a[i]) - float(b[i])) <= tol for i in range(len(a)))


def _round_vec(value: Any, digits: int = 6) -> list[float]:
    return [round(float(value[0]), digits), round(float(value[1]), digits), round(float(value[2]), digits)]


def _round_matrix(value: list[list[float]], digits: int = 6) -> list[list[float]]:
    return [[round(float(item), digits) for item in row] for row in value]


def _failure(assembly: str, stage: str, error_type: str, message: str) -> dict:
    return {
        "ok": False,
        "stage": stage,
        "assembly": assembly,
        "error": {"type": error_type, "message": message},
    }
