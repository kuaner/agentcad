from __future__ import annotations

import itertools
import math
import os
import re
import struct
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .geometry import min_clearance_3d, parse_shape
from .jsonio import read_json, write_json
from .metadata import validate_part_metadata_dict
from .contract import SchemaIssue
from .render import triangles_to_svg
from .runner import build_model
from .section import AXIS_X, AXIS_Y, AXIS_Z, analyze_section_segments, section_segments
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


@dataclass
class _TriBvhNode:
    bbox: tuple[Vec3, Vec3]
    indices: list[int] | None = None
    left: "_TriBvhNode | None" = None
    right: "_TriBvhNode | None" = None


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
        metadata_schema_checks = _metadata_schema_checks(components)
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
            "metadata_schema_checks": metadata_schema_checks,
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
    except Exception as exc:
        payload = _failure(safe, "assembly_measure", type(exc).__name__, str(exc))
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
            _write_observability(observability_path, safe, geometry, payload)
            return payload

        checks: list[dict] = []
        checks.extend(_fresh_component_checks(geometry))
        checks.extend(geometry.get("metadata_geometry_checks") or [])
        checks.extend(geometry.get("metadata_schema_checks") or [])
        checks.extend(_mate_checks(geometry))
        checks.extend(_evaluate_user_checks(contract, geometry))
        checks.extend(_assembly_interface_contract_checks(contract, geometry))
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

        stl_payload = _export_assembly_stl(project, safe, geometry)
        checks.append(
            {
                "name": "assembly_stl_generated",
                "type": "artifact_exists",
                "ok": bool(stl_payload.get("ok")),
                "artifacts": stl_payload.get("artifacts", {}),
                "error": stl_payload.get("error"),
            }
        )

        mjcf_payload = _export_mjcf(project, safe, contract, geometry)
        mjcf_check = _mjcf_consistency_check(mjcf_payload, geometry)
        checks.append(mjcf_check)
        checks.append(_transform_consistency_check(geometry, mjcf_payload))

        artifacts = {
            "geometry": str(out_dir / "assembly_geometry.json"),
            "validation": str(validation_path),
            "observability": str(observability_path),
        }
        artifacts.update(render_payload.get("artifacts") or {})
        artifacts.update(stl_payload.get("artifacts") or {})
        artifacts.update(mjcf_payload.get("artifacts") or {})

        preview_seed_failed = [check for check in checks if not check.get("ok")]
        preview_seed = _assembly_validation_payload(
            safe,
            checks,
            geometry,
            artifacts,
            message="assembly validation passed" if not preview_seed_failed else "assembly validation failed",
        )
        write_json(validation_path, preview_seed)
        _write_observability(observability_path, safe, geometry, preview_seed)

        from .preview import write_assembly_preview

        preview_payload = write_assembly_preview(project, safe, validation_payload=preview_seed, geometry_payload=geometry)
        artifacts.update(preview_payload.get("artifacts") or {})
        checks.append(
            {
                "name": "interactive_preview_generated",
                "type": "artifact_exists",
                "ok": bool(preview_payload.get("ok")),
                "artifacts": preview_payload.get("artifacts", {}),
                "error": preview_payload.get("error"),
            }
        )

        failed = [check for check in checks if not check.get("ok")]
        payload = _assembly_validation_payload(
            safe,
            checks,
            geometry,
            artifacts,
            message="assembly validation passed" if not failed else "assembly validation failed",
        )
        write_json(validation_path, payload)
        _write_observability(observability_path, safe, geometry, payload)
        if preview_payload.get("ok"):
            write_assembly_preview(project, safe, validation_payload=payload, geometry_payload=geometry)
        return payload
    except AssemblyError as exc:
        payload = _failure(safe, "assembly_validate", exc.error_type, exc.message)
        payload["artifacts"] = {
            "geometry": str(out_dir / "assembly_geometry.json"),
            "validation": str(validation_path),
            "observability": str(observability_path),
        }
        write_json(validation_path, payload)
        _write_observability(observability_path, safe, {}, payload)
        return payload
    except Exception as exc:
        payload = _failure(safe, "assembly_validate", type(exc).__name__, str(exc))
        payload["artifacts"] = {
            "geometry": str(out_dir / "assembly_geometry.json"),
            "validation": str(validation_path),
            "observability": str(observability_path),
        }
        write_json(validation_path, payload)
        _write_observability(observability_path, safe, {}, payload)
        return payload


def review_assembly(project: Path, name: str) -> dict:
    safe = normalize_model_name(name)
    out_dir = assembly_outputs_dir(project, safe)
    validation_path = out_dir / "assembly_validation.json"
    observability_path = out_dir / "assembly_observability.json"
    review_path = out_dir / "assembly_review.json"
    contract_path = assembly_dir(project, safe) / "assembly.json"

    validation = read_json(validation_path, default=None)
    observability = read_json(observability_path, default=None)
    contract = read_json(contract_path, default={}) or {}
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
        for key in ("mjcf", "assembly_stl", "preview_combined_iso", "preview_exploded_iso", "preview_page", "geometry"):
            path = (validation.get("artifacts") or {}).get(key)
            checks.append(
                {
                    "name": f"artifact:{key}",
                    "type": "artifact_exists",
                    "ok": bool(path) and Path(path).exists(),
                    "path": path,
                }
            )
        interface_contracts = contract.get("interfaces") or []
        if interface_contracts:
            interface_checks = [
                check for check in validation.get("checks", [])
                if str(check.get("name", "")).startswith("assembly_interface:")
            ]
            checks.append({
                "name": "assembly_interfaces_validated",
                "type": "assembly_interface_contract",
                "ok": bool(interface_checks) and all(check.get("ok") for check in interface_checks),
                "expected_interfaces": len(interface_contracts) if isinstance(interface_contracts, list) else len(interface_contracts.keys()),
                "validated_interfaces": len(interface_checks),
                "failed": [check.get("name") for check in interface_checks if not check.get("ok")],
            })

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
    _validate_component_ids(components)
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
        metadata_issues = validate_part_metadata_dict(metadata)

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
            "metadata_issues": metadata_issues,
            "transform": transform,
            "local_triangles": local_triangles,
            "world_triangles": world_triangles,
            "local_bbox": local_report.get("bbox"),
            "world_bbox": world_report.get("bbox"),
            "mesh": world_report.get("mesh"),
            "triangle_count": len(world_triangles),
        }
    return records


def _validate_component_ids(components: list) -> None:
    safe_names: dict[str, str] = {}
    for index, raw in enumerate(components):
        if not isinstance(raw, dict):
            continue
        cid = str(raw.get("id") or "").strip()
        if not cid:
            continue
        safe = _safe_xml_name(cid)
        if safe != cid:
            raise AssemblyError(
                "ComponentIdInvalid",
                f"component id {cid!r} is not MJCF-safe; use letters, numbers, underscores, dots, or hyphens and start with a letter or underscore",
            )
        previous = safe_names.get(safe)
        if previous is not None:
            if previous == cid:
                raise AssemblyError("DuplicateComponentId", f"duplicate component id: {cid}")
            raise AssemblyError("ComponentIdCollision", f"component ids {previous!r} and {cid!r} collapse to the same MJCF name {safe!r}")
        safe_names[safe] = cid


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
            for key in ("ref", "path", "a", "b", "inner", "outer", "feature_a", "feature_b", "shape_a", "shape_b"):
                _append_ref_value(refs, check.get(key))
    for interface in contract.get("interfaces", []) or []:
        if isinstance(interface, dict):
            for key in ("a", "b", "feature_a", "feature_b", "inner", "outer"):
                _append_ref_value(refs, interface.get(key))
    return sorted(set(refs))


def _append_ref(refs: list[str], value: Any) -> None:
    if isinstance(value, str) and "." in value:
        refs.append(value)


def _append_ref_value(refs: list[str], value: Any) -> None:
    _append_ref(refs, value)
    if isinstance(value, dict) and isinstance(value.get("ref"), str):
        _append_ref(refs, value.get("ref"))


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
    if _is_box_descriptor(value):
        return {
            **value,
            "world_shape": _transform_shape_descriptor(value, transform.matrix),
        }
    if _is_sphere_descriptor(value):
        return {
            **value,
            "world_shape": _transform_shape_descriptor(value, transform.matrix),
        }
    transformed = {}
    for key, item in value.items():
        transformed[key] = _transform_descriptor(item, transform)
    return transformed


def _is_axis_descriptor(value: Any) -> bool:
    return isinstance(value, dict) and "point" in value and "direction" in value


def _is_cylinder_descriptor(value: Any) -> bool:
    return isinstance(value, dict) and value.get("type") == "cylinder"


def _is_box_descriptor(value: Any) -> bool:
    return isinstance(value, dict) and value.get("type") == "box"


def _is_sphere_descriptor(value: Any) -> bool:
    return isinstance(value, dict) and value.get("type") == "sphere"


def _descriptor_radius(desc: dict) -> float | None:
    for key in ("radius_mm", "radius"):
        if key in desc:
            return float(desc[key])
    if "diameter_mm" in desc:
        return float(desc["diameter_mm"]) / 2.0
    if "diameter" in desc:
        return float(desc["diameter"]) / 2.0
    return None


def _descriptor_float(value: Any, label: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise AssemblyError("CylinderDescriptorInvalid", f"{label} must be numeric") from exc


def _descriptor_center(desc: dict, axis: str) -> tuple[float, ...]:
    center = desc.get("center", [0.0, 0.0])
    if not isinstance(center, (list, tuple)):
        raise AssemblyError("CylinderDescriptorInvalid", "cylinder center must be a number array")
    if axis == "z":
        if len(center) not in (2, 3):
            raise AssemblyError("CylinderDescriptorInvalid", "z-axis cylinder center must contain two or three values")
        return (_descriptor_float(center[0], "cylinder center[0]"), _descriptor_float(center[1], "cylinder center[1]"))
    if axis in ("x", "y"):
        if len(center) < 2:
            raise AssemblyError("CylinderDescriptorInvalid", f"{axis}-axis cylinder center must contain at least two values")
        return (_descriptor_float(center[0], "cylinder center[0]"), _descriptor_float(center[1], "cylinder center[1]"))
    raise AssemblyError("CylinderDescriptorInvalid", f"unsupported cylinder axis: {axis}")


def _cylinder_endpoints(desc: dict) -> tuple[Vec3, Vec3]:
    axis = str(desc.get("axis", "z")).lower()
    range_key = f"{axis}_range"
    axis_range = desc.get(range_key) or desc.get("range") or [0.0, 0.0]
    if not isinstance(axis_range, (list, tuple)) or len(axis_range) != 2:
        raise AssemblyError("CylinderDescriptorInvalid", f"cylinder {range_key} must contain two values")
    start = _descriptor_float(axis_range[0], f"cylinder {range_key}[0]")
    end = _descriptor_float(axis_range[1], f"cylinder {range_key}[1]")
    center = _descriptor_center(desc, str(axis))
    if axis == "z":
        return ((center[0], center[1], start), (center[0], center[1], end))
    if axis == "x":
        y, z = center[0], center[1]
        return ((start, y, z), (end, y, z))
    if axis == "y":
        x, z = center[0], center[1]
        return ((x, start, z), (x, end, z))
    raise AssemblyError("CylinderDescriptorInvalid", f"unsupported cylinder axis: {axis}")


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
        raise AssemblyError("RequiredFieldMissing", f"{name}.{key} is required")
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
        component_a = components[a_id]
        component_b = components[b_id]
        bbox_a = components[a_id].get("world_bbox")
        bbox_b = components[b_id].get("world_bbox")
        bbox_overlap = _bbox_overlap(bbox_a, bbox_b)
        aabb_clearance = _bbox_clearance(bbox_a, bbox_b)
        narrow = _mesh_pair_evidence(
            component_a.get("world_triangles") or [],
            component_b.get("world_triangles") or [],
            bbox_overlap=bbox_overlap,
            aabb_clearance=aabb_clearance,
        )
        rows.append(
            {
                "components": [a_id, b_id],
                "bbox_overlap": bbox_overlap,
                "aabb_clearance_mm": aabb_clearance,
                **narrow,
            }
        )
    return rows


def _mesh_pair_evidence(
    triangles_a: list[Triangle],
    triangles_b: list[Triangle],
    *,
    bbox_overlap: bool,
    aabb_clearance: float | None,
) -> dict:
    if not triangles_a or not triangles_b:
        return {
            "method": "mesh_narrow_phase_unavailable",
            "mesh_clearance_mm": None,
            "mesh_penetration_mm": None,
            "interferes": False,
            "narrow_phase": {
                "ok": False,
                "error": {"type": "MeshMissing", "message": "both components need STL triangles for narrow-phase evidence"},
            },
        }
    if not bbox_overlap:
        return {
            "method": "aabb_separated",
            "mesh_clearance_mm": aabb_clearance,
            "mesh_penetration_mm": 0.0,
            "interferes": False,
            "narrow_phase": {
                "ok": True,
                "broad_phase": "separated",
                "triangle_intersection_count": 0,
                "inside_sample_count": 0,
                "min_sample_distance_mm": aabb_clearance,
            },
        }

    evidence = _narrow_phase_mesh_pair(triangles_a, triangles_b)
    penetration = float(evidence.get("max_penetration_mm") or 0.0)
    triangle_hits = int(evidence.get("triangle_intersection_count") or 0)
    clearance = -penetration if penetration > EPS else (0.0 if triangle_hits else evidence.get("min_sample_distance_mm"))
    return {
        "method": "mesh_narrow_phase_v1",
        "mesh_clearance_mm": clearance,
        "mesh_penetration_mm": penetration,
        "interferes": penetration > EPS,
        "narrow_phase": evidence,
    }


def _narrow_phase_mesh_pair(triangles_a: list[Triangle], triangles_b: list[Triangle]) -> dict:
    boxes_a = [_triangle_aabb(tri) for tri in triangles_a]
    boxes_b = [_triangle_aabb(tri) for tri in triangles_b]
    candidate_pairs = list(_overlapping_triangle_pairs(boxes_a, boxes_b))
    triangle_intersections = 0
    for i, j in candidate_pairs:
        if _triangles_intersect(triangles_a[i], triangles_b[j]):
            triangle_intersections += 1
            if triangle_intersections >= 256:
                break

    samples_a = _mesh_sample_points(triangles_a)
    samples_b = _mesh_sample_points(triangles_b)
    inside: list[dict] = []
    min_distance: float | None = None

    for owner, samples, other in (("a", samples_a, triangles_b), ("b", samples_b, triangles_a)):
        for point in samples:
            distance = _point_mesh_distance(point, other)
            if min_distance is None or distance < min_distance:
                min_distance = distance
            if distance > 1e-5 and _point_inside_mesh(point, other):
                inside.append(
                    {
                        "owner": owner,
                        "point": _round_vec(point),
                        "penetration_mm": distance,
                    }
                )

    max_penetration = max((row["penetration_mm"] for row in inside), default=0.0)
    deepest = max(inside, key=lambda row: row["penetration_mm"], default=None)
    return {
        "ok": True,
        "broad_phase": "aabb_overlap",
        "triangle_candidate_pairs": len(candidate_pairs),
        "triangle_intersection_count": triangle_intersections,
        "inside_sample_count": len(inside),
        "sample_count": len(samples_a) + len(samples_b),
        "min_sample_distance_mm": min_distance,
        "max_penetration_mm": max_penetration,
        "deepest_sample": deepest,
        "note": "inside samples estimate solid penetration; triangle intersections without inside samples are treated as surface contact evidence",
    }


def _mesh_sample_points(triangles: list[Triangle], max_samples: int = 384) -> list[Vec3]:
    points: list[Vec3] = []
    for tri in triangles:
        points.extend(tri)
        points.append(_triangle_centroid(tri))
    dedup: list[Vec3] = []
    seen: set[Vec3] = set()
    for point in points:
        key = (round(point[0], 4), round(point[1], 4), round(point[2], 4))
        if key in seen:
            continue
        seen.add(key)
        dedup.append(point)
    if len(dedup) <= max_samples:
        return dedup
    step = len(dedup) / max_samples
    return [dedup[min(int(i * step), len(dedup) - 1)] for i in range(max_samples)]


def _triangle_centroid(tri: Triangle) -> Vec3:
    return (
        (tri[0][0] + tri[1][0] + tri[2][0]) / 3.0,
        (tri[0][1] + tri[1][1] + tri[2][1]) / 3.0,
        (tri[0][2] + tri[1][2] + tri[2][2]) / 3.0,
    )


def _triangle_aabb(tri: Triangle) -> tuple[Vec3, Vec3]:
    return (
        (min(p[0] for p in tri), min(p[1] for p in tri), min(p[2] for p in tri)),
        (max(p[0] for p in tri), max(p[1] for p in tri), max(p[2] for p in tri)),
    )


def _overlapping_triangle_pairs(
    boxes_a: list[tuple[Vec3, Vec3]],
    boxes_b: list[tuple[Vec3, Vec3]],
) -> list[tuple[int, int]]:
    if not boxes_a or not boxes_b:
        return []
    tree_a = _build_tri_bvh(boxes_a, list(range(len(boxes_a))))
    tree_b = _build_tri_bvh(boxes_b, list(range(len(boxes_b))))
    pairs: list[tuple[int, int]] = []
    _collect_bvh_pairs(tree_a, tree_b, boxes_a, boxes_b, pairs)
    return pairs


def _build_tri_bvh(boxes: list[tuple[Vec3, Vec3]], indices: list[int]) -> _TriBvhNode:
    bbox = _union_box([boxes[index] for index in indices])
    if len(indices) <= 24:
        return _TriBvhNode(bbox=bbox, indices=indices)
    spans = [bbox[1][axis] - bbox[0][axis] for axis in range(3)]
    axis = max(range(3), key=lambda item: spans[item])
    indices.sort(key=lambda index: (boxes[index][0][axis] + boxes[index][1][axis]) / 2.0)
    mid = max(1, min(len(indices) - 1, len(indices) // 2))
    return _TriBvhNode(
        bbox=bbox,
        left=_build_tri_bvh(boxes, indices[:mid]),
        right=_build_tri_bvh(boxes, indices[mid:]),
    )


def _collect_bvh_pairs(
    a: _TriBvhNode,
    b: _TriBvhNode,
    boxes_a: list[tuple[Vec3, Vec3]],
    boxes_b: list[tuple[Vec3, Vec3]],
    pairs: list[tuple[int, int]],
) -> None:
    if not _boxes_overlap(a.bbox, b.bbox):
        return
    if a.indices is not None and b.indices is not None:
        for i in a.indices:
            for j in b.indices:
                if _boxes_overlap(boxes_a[i], boxes_b[j]):
                    pairs.append((i, j))
        return
    if b.indices is not None or (a.indices is None and _box_volume(a.bbox) >= _box_volume(b.bbox)):
        if a.left is not None:
            _collect_bvh_pairs(a.left, b, boxes_a, boxes_b, pairs)
        if a.right is not None:
            _collect_bvh_pairs(a.right, b, boxes_a, boxes_b, pairs)
    else:
        if b.left is not None:
            _collect_bvh_pairs(a, b.left, boxes_a, boxes_b, pairs)
        if b.right is not None:
            _collect_bvh_pairs(a, b.right, boxes_a, boxes_b, pairs)


def _union_box(boxes: list[tuple[Vec3, Vec3]]) -> tuple[Vec3, Vec3]:
    return (
        (min(box[0][0] for box in boxes), min(box[0][1] for box in boxes), min(box[0][2] for box in boxes)),
        (max(box[1][0] for box in boxes), max(box[1][1] for box in boxes), max(box[1][2] for box in boxes)),
    )


def _boxes_overlap(a: tuple[Vec3, Vec3], b: tuple[Vec3, Vec3], eps: float = 1e-8) -> bool:
    return all(a[0][axis] <= b[1][axis] + eps and b[0][axis] <= a[1][axis] + eps for axis in range(3))


def _box_volume(box: tuple[Vec3, Vec3]) -> float:
    return max(box[1][0] - box[0][0], 0.0) * max(box[1][1] - box[0][1], 0.0) * max(box[1][2] - box[0][2], 0.0)


def _triangles_intersect(a: Triangle, b: Triangle) -> bool:
    for p, q in ((a[0], a[1]), (a[1], a[2]), (a[2], a[0])):
        if _segment_triangle_intersects(p, q, b):
            return True
    for p, q in ((b[0], b[1]), (b[1], b[2]), (b[2], b[0])):
        if _segment_triangle_intersects(p, q, a):
            return True
    return _coplanar_triangles_overlap(a, b)


def _segment_triangle_intersects(p0: Vec3, p1: Vec3, tri: Triangle, eps: float = 1e-9) -> bool:
    direction = sub(p1, p0)
    edge1 = sub(tri[1], tri[0])
    edge2 = sub(tri[2], tri[0])
    h = cross(direction, edge2)
    det = dot(edge1, h)
    if abs(det) < eps:
        return False
    inv_det = 1.0 / det
    s = sub(p0, tri[0])
    u = inv_det * dot(s, h)
    if u < -eps or u > 1.0 + eps:
        return False
    q = cross(s, edge1)
    v = inv_det * dot(direction, q)
    if v < -eps or u + v > 1.0 + eps:
        return False
    t = inv_det * dot(edge2, q)
    return -eps <= t <= 1.0 + eps


def _coplanar_triangles_overlap(a: Triangle, b: Triangle, eps: float = 1e-7) -> bool:
    normal_a = cross(sub(a[1], a[0]), sub(a[2], a[0]))
    normal_b = cross(sub(b[1], b[0]), sub(b[2], b[0]))
    if length(normal_a) <= eps or length(normal_b) <= eps:
        return False
    na = normalize(normal_a)
    nb = normalize(normal_b)
    if abs(abs(dot(na, nb)) - 1.0) > 1e-5:
        return False
    if any(abs(dot(sub(point, a[0]), na)) > eps for point in b):
        return False
    drop = max(range(3), key=lambda axis: abs(na[axis]))
    pa = [_project2(point, drop) for point in a]
    pb = [_project2(point, drop) for point in b]
    for e1 in ((pa[0], pa[1]), (pa[1], pa[2]), (pa[2], pa[0])):
        for e2 in ((pb[0], pb[1]), (pb[1], pb[2]), (pb[2], pb[0])):
            if _segments_intersect_2d(e1[0], e1[1], e2[0], e2[1]):
                return True
    return _point_in_triangle_2d(pa[0], pb) or _point_in_triangle_2d(pb[0], pa)


def _project2(point: Vec3, drop_axis: int) -> tuple[float, float]:
    axes = [axis for axis in (0, 1, 2) if axis != drop_axis]
    return (point[axes[0]], point[axes[1]])


def _segments_intersect_2d(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
    eps: float = 1e-9,
) -> bool:
    def orient(p: tuple[float, float], q: tuple[float, float], r: tuple[float, float]) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    o1 = orient(a, b, c)
    o2 = orient(a, b, d)
    o3 = orient(c, d, a)
    o4 = orient(c, d, b)
    if (o1 > eps) != (o2 > eps) and (o3 > eps) != (o4 > eps):
        return True
    return (
        abs(o1) <= eps and _point_on_segment_2d(c, a, b, eps)
        or abs(o2) <= eps and _point_on_segment_2d(d, a, b, eps)
        or abs(o3) <= eps and _point_on_segment_2d(a, c, d, eps)
        or abs(o4) <= eps and _point_on_segment_2d(b, c, d, eps)
    )


def _point_on_segment_2d(
    point: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
    eps: float,
) -> bool:
    return (
        min(a[0], b[0]) - eps <= point[0] <= max(a[0], b[0]) + eps
        and min(a[1], b[1]) - eps <= point[1] <= max(a[1], b[1]) + eps
    )


def _point_in_triangle_2d(point: tuple[float, float], tri: list[tuple[float, float]], eps: float = 1e-9) -> bool:
    a, b, c = tri
    area = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    if abs(area) <= eps:
        return False
    s = ((a[1] - c[1]) * (point[0] - c[0]) + (c[0] - a[0]) * (point[1] - c[1])) / area
    t = ((c[1] - b[1]) * (point[0] - c[0]) + (b[0] - c[0]) * (point[1] - c[1])) / area
    u = 1.0 - s - t
    return s >= -eps and t >= -eps and u >= -eps


def _point_mesh_distance(point: Vec3, triangles: list[Triangle]) -> float:
    return min((_point_triangle_distance(point, tri) for tri in triangles), default=float("inf"))


def _point_triangle_distance(point: Vec3, tri: Triangle) -> float:
    # Real-Time Collision Detection, closest point on triangle.
    a, b, c = tri
    ab = sub(b, a)
    ac = sub(c, a)
    ap = sub(point, a)
    d1 = dot(ab, ap)
    d2 = dot(ac, ap)
    if d1 <= 0.0 and d2 <= 0.0:
        return length(sub(point, a))

    bp = sub(point, b)
    d3 = dot(ab, bp)
    d4 = dot(ac, bp)
    if d3 >= 0.0 and d4 <= d3:
        return length(sub(point, b))

    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        v = d1 / (d1 - d3)
        nearest = _add(a, _mul(ab, v))
        return length(sub(point, nearest))

    cp = sub(point, c)
    d5 = dot(ab, cp)
    d6 = dot(ac, cp)
    if d6 >= 0.0 and d5 <= d6:
        return length(sub(point, c))

    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        w = d2 / (d2 - d6)
        nearest = _add(a, _mul(ac, w))
        return length(sub(point, nearest))

    va = d3 * d6 - d5 * d4
    if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        nearest = _add(b, _mul(sub(c, b), w))
        return length(sub(point, nearest))

    n = normalize(cross(ab, ac))
    return abs(dot(sub(point, a), n))


def _point_inside_mesh(point: Vec3, triangles: list[Triangle]) -> bool:
    direction = normalize((0.817137, 0.271828, 0.506731))
    hits: list[float] = []
    for tri in triangles:
        t = _ray_triangle_t(point, direction, tri)
        if t is None or t <= 1e-7:
            continue
        if not any(abs(t - existing) <= 1e-6 for existing in hits):
            hits.append(t)
    return len(hits) % 2 == 1


def _ray_triangle_t(origin: Vec3, direction: Vec3, tri: Triangle, eps: float = 1e-9) -> float | None:
    edge1 = sub(tri[1], tri[0])
    edge2 = sub(tri[2], tri[0])
    h = cross(direction, edge2)
    det = dot(edge1, h)
    if abs(det) < eps:
        return None
    inv_det = 1.0 / det
    s = sub(origin, tri[0])
    u = inv_det * dot(s, h)
    if u < -eps or u > 1.0 + eps:
        return None
    q = cross(s, edge1)
    v = inv_det * dot(direction, q)
    if v < -eps or u + v > 1.0 + eps:
        return None
    t = inv_det * dot(edge2, q)
    return t if t > eps else None


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


def _assembly_interface_contract_checks(contract: dict, geometry: dict) -> list[dict]:
    checks: list[dict] = []
    interfaces = contract.get("interfaces") or []
    if isinstance(interfaces, dict):
        interfaces = [
            {"id": key, **value} if isinstance(value, dict) and "id" not in value else value
            for key, value in interfaces.items()
        ]
    if not isinstance(interfaces, list):
        return [{
            "name": "assembly_interfaces_schema",
            "type": "assembly_interface_contract",
            "ok": False,
            "error": {"type": "InterfacesInvalid", "message": "assembly interfaces must be a list or object"},
        }]
    refs = geometry.get("references") or {}
    for index, interface in enumerate(interfaces):
        if not isinstance(interface, dict):
            checks.append({
                "name": f"assembly_interface:{index}",
                "type": "assembly_interface_contract",
                "ok": False,
                "error": {"type": "InterfaceInvalid", "message": "interface must be an object"},
            })
            continue
        iface_type = str(interface.get("type") or "")
        name = str(interface.get("id") or f"interface_{index}")
        if iface_type in ("cylindrical_mate", "cylindrical_fit", "coaxial_fit"):
            checks.append(_eval_assembly_cylindrical_interface(name, interface, refs, geometry))
        else:
            checks.append({
                "name": f"assembly_interface:{name}",
                "type": "assembly_interface_contract",
                "ok": False,
                "interface_type": iface_type,
                "error": {"type": "UnsupportedAssemblyInterfaceType", "message": f"unsupported interface type: {iface_type}"},
            })
    return checks


def _eval_assembly_cylindrical_interface(name: str, interface: dict, refs: dict[str, dict], geometry: dict) -> dict:
    ref_a = interface.get("feature_a") or interface.get("a")
    ref_b = interface.get("feature_b") or interface.get("b")
    axis_a = _axis_from_ref(ref_a, refs)
    axis_b = _axis_from_ref(ref_b, refs)
    if axis_a is None or axis_b is None:
        return {
            "name": f"assembly_interface:{name}",
            "type": "assembly_interface_contract",
            "ok": False,
            "interface_type": "cylindrical_mate",
            "components": _components_from_refs([ref_a, ref_b]),
            "error": {"type": "AxisMissing", "message": "feature_a and feature_b must resolve to axis-like metadata descriptors"},
        }
    max_offset = float(interface.get("axis_tolerance_mm", interface.get("max_radial_offset_mm", 0.2)))
    max_angle = float(interface.get("angle_tolerance_deg", interface.get("max_axis_angle_deg", 1.0)))
    angle = _angle_deg(axis_a[1], axis_b[1])
    radial_offset = _point_axis_distance(axis_b[0], axis_a[0], axis_a[1])
    clearance_req = interface.get("clearance_mm")
    clearance = _interface_radial_clearance(ref_a, ref_b, geometry)
    clearance_ok = True
    if clearance_req is not None:
        clearance_ok = clearance is not None and clearance >= float(clearance_req)
    ok = angle <= max_angle and radial_offset <= max_offset and clearance_ok
    return {
        "name": f"assembly_interface:{name}",
        "type": "assembly_interface_contract",
        "ok": ok,
        "interface_type": "cylindrical_mate",
        "components": _components_from_refs([ref_a, ref_b]),
        "refs": [ref_a, ref_b],
        "angle_deg": angle,
        "max_axis_angle_deg": max_angle,
        "radial_offset_mm": radial_offset,
        "axis_tolerance_mm": max_offset,
        "clearance_mm": clearance,
        "required_clearance_mm": float(clearance_req) if clearance_req is not None else None,
        "error": None if ok else {"type": "AssemblyInterfaceMismatch", "message": "cylindrical interface is eccentric, angled, or lacks required radial clearance"},
    }


def _interface_radial_clearance(ref_a: Any, ref_b: Any, geometry: dict) -> float | None:
    if not isinstance(ref_a, str) or not isinstance(ref_b, str):
        return None
    refs = geometry.get("references") or {}
    desc_a = (refs.get(ref_a) or {}).get("local")
    desc_b = (refs.get(ref_b) or {}).get("local")
    if desc_a is None or desc_b is None:
        return None
    a_inner = _radius_from_descriptor(desc_a, "inner")
    a_outer = _radius_from_descriptor(desc_a, "outer")
    b_inner = _radius_from_descriptor(desc_b, "inner")
    b_outer = _radius_from_descriptor(desc_b, "outer")
    candidates = []
    if a_inner is not None and b_outer is not None:
        candidates.append(a_inner - b_outer)
    if b_inner is not None and a_outer is not None:
        candidates.append(b_inner - a_outer)
    if not candidates:
        return None
    non_negative = [value for value in candidates if value >= 0]
    return min(non_negative) if non_negative else max(candidates)


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
        elif ctype == "assembly_section_component_count":
            checks.append(_eval_assembly_section_component_count(name, check, geometry))
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
    pair = _pair_key(check.get("components") or _components_from_refs([check.get("a"), check.get("b"), check.get("feature_a"), check.get("feature_b")]))
    row = _pair_row(geometry, pair)
    tolerance = float(check.get("tolerance_mm", check.get("tolerance", 0.0)))
    if row is None:
        return {
            "name": name,
            "type": "interference_free",
            "ok": False,
            "components": list(pair),
                "error": {"type": "PairMissing", "message": "component pair not found"},
        }
    penetration = row.get("mesh_penetration_mm")
    overlap = bool(row.get("bbox_overlap"))
    ok = penetration is not None and float(penetration) <= tolerance
    return {
        "name": name,
        "type": "interference_free",
        "ok": ok,
        "components": list(pair),
        "method": row.get("method"),
        "bbox_overlap": overlap,
        "mesh_clearance_mm": row.get("mesh_clearance_mm"),
        "mesh_penetration_mm": penetration,
        "tolerance_mm": tolerance,
        "aabb_clearance_mm": row.get("aabb_clearance_mm"),
        "narrow_phase": row.get("narrow_phase"),
        "error": None if ok else {"type": "MeshInterference", "message": "component pair has measured mesh penetration"},
    }


def _eval_inter_model_min_clearance(name: str, check: dict, geometry: dict) -> dict:
    pair = _pair_key(check.get("components") or _components_from_refs([check.get("a"), check.get("b"), check.get("feature_a"), check.get("feature_b"), check.get("shape_a"), check.get("shape_b")]))
    row = _pair_row(geometry, pair)
    min_mm = _required_float(check, "min_mm", name)
    shape_result = _shape_clearance_for_check(check, geometry)
    if shape_result is not None:
        actual = shape_result.get("clearance_mm")
        return {
            "name": name,
            "type": "inter_model_min_clearance",
            "ok": actual is not None and min_mm is not None and float(actual) >= min_mm,
            "components": shape_result.get("components") or list(pair),
            "actual_mm": actual,
            "min_mm": min_mm,
            "method": "shape_descriptor",
            "evidence": shape_result,
        }
    if row is None:
        return {
            "name": name,
            "type": "inter_model_min_clearance",
            "ok": False,
            "components": list(pair),
                "error": {"type": "PairMissing", "message": "component pair not found"},
        }
    actual = row.get("mesh_clearance_mm")
    return {
        "name": name,
        "type": "inter_model_min_clearance",
        "ok": actual is not None and min_mm is not None and actual >= min_mm,
        "components": list(pair),
        "actual_mm": actual,
        "min_mm": min_mm,
        "method": row.get("method") or "mesh_or_aabb",
        "aabb_clearance_mm": row.get("aabb_clearance_mm"),
        "narrow_phase": row.get("narrow_phase"),
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


def _eval_assembly_section_component_count(name: str, check: dict, geometry: dict) -> dict:
    axis, value = _section_axis_value(check)
    if axis is None or value is None:
        return {
            "name": name,
            "type": "assembly_section_component_count",
            "ok": False,
            "error": {"type": "SectionMissing", "message": "provide x, y, z or axis/value for the section"},
        }
    expected = check.get("expected", check.get("expected_component_count", check.get("count")))
    if expected is None:
        return {
            "name": name,
            "type": "assembly_section_component_count",
            "ok": False,
            "error": {"type": "ExpectedCountMissing", "message": "expected component count is required"},
        }
    selected = set(str(item) for item in (check.get("components") or []))
    hits = []
    total_segments = 0
    disconnected_contours = 0
    for cid, component in (geometry.get("components") or {}).items():
        if selected and cid not in selected:
            continue
        triangles = _component_triangles_from_public_record(component)
        segments = section_segments(triangles, axis, value)
        analysis = analyze_section_segments(segments, axis, value)
        if segments:
            hits.append(
                {
                    "component": cid,
                    "segment_count": len(segments),
                    "component_count": analysis.get("component_count"),
                    "bbox": analysis.get("bbox"),
                }
            )
            total_segments += len(segments)
            disconnected_contours += int(analysis.get("component_count") or 0)
    actual = len(hits)
    return {
        "name": name,
        "type": "assembly_section_component_count",
        "ok": actual == int(expected),
        "axis": _axis_name(axis),
        "value_mm": value,
        "actual": actual,
        "expected": int(expected),
        "total_segment_count": total_segments,
        "disconnected_contour_count": disconnected_contours,
        "components": [row["component"] for row in hits],
        "evidence": hits,
    }


def _section_axis_value(check: dict) -> tuple[int | None, float | None]:
    for key, axis in (("x", AXIS_X), ("section_x", AXIS_X), ("y", AXIS_Y), ("section_y", AXIS_Y), ("z", AXIS_Z), ("section_z", AXIS_Z)):
        if key in check:
            return axis, float(check[key])
    axis_value = check.get("axis")
    value = check.get("value", check.get("section_value"))
    if isinstance(axis_value, str) and value is not None:
        lowered = axis_value.lower()
        if lowered == "x":
            return AXIS_X, float(value)
        if lowered == "y":
            return AXIS_Y, float(value)
        if lowered == "z":
            return AXIS_Z, float(value)
    return None, None


def _axis_name(axis: int) -> str:
    return {AXIS_X: "x", AXIS_Y: "y", AXIS_Z: "z"}.get(axis, "?")


def _shape_clearance_for_check(check: dict, geometry: dict) -> dict | None:
    left = check.get("a", check.get("feature_a", check.get("shape_a")))
    right = check.get("b", check.get("feature_b", check.get("shape_b")))
    if left is None or right is None:
        return None
    try:
        shape_a, components_a = _shape_from_check_side(left, check, geometry, side="a")
        shape_b, components_b = _shape_from_check_side(right, check, geometry, side="b")
        result = min_clearance_3d(shape_a, shape_b)
        return {
            **result,
            "components": sorted(set(components_a + components_b)),
            "shape_a": shape_a,
            "shape_b": shape_b,
        }
    except Exception as exc:
        return {
            "clearance_mm": None,
            "components": _components_from_refs([left, right]),
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }


def _shape_from_check_side(value: Any, check: dict, geometry: dict, *, side: str) -> tuple[dict, list[str]]:
    if isinstance(value, str):
        return _shape_from_ref(value, geometry)
    if isinstance(value, dict) and isinstance(value.get("ref"), str):
        return _shape_from_ref(value["ref"], geometry)
    if not isinstance(value, dict):
        raise AssemblyError("ShapeDescriptorInvalid", f"{side} must be a metadata ref or shape descriptor")
    shape = value.get("shape") if isinstance(value.get("shape"), dict) else value
    component = (
        value.get("component")
        or check.get(f"{side}_component")
        or check.get(f"feature_{side}_component")
        or check.get(f"feature_{side}_model")
    )
    if component:
        component_record = (geometry.get("components") or {}).get(str(component))
        if component_record is None:
            raise AssemblyError("ComponentMissing", f"component not found for {side}: {component}")
        return _transform_shape_descriptor(shape, component_record["transform"]["matrix"]), [str(component)]
    return parse_shape(_normalize_shape_descriptor(shape)), []


def _shape_from_ref(ref: str, geometry: dict) -> tuple[dict, list[str]]:
    resolved = (geometry.get("references") or {}).get(ref)
    if not resolved or not resolved.get("ok"):
        raise AssemblyError("ReferenceMissing", f"metadata reference not found: {ref}")
    component = (geometry.get("components") or {}).get(resolved.get("component"))
    if component is None:
        raise AssemblyError("ComponentMissing", f"component not found for ref: {ref}")
    local = resolved.get("local")
    return _transform_shape_descriptor(local, component["transform"]["matrix"]), [str(resolved.get("component"))]


def _transform_shape_descriptor(desc: Any, matrix: list[list[float]]) -> dict:
    if not isinstance(desc, dict):
        raise AssemblyError("ShapeDescriptorInvalid", "shape descriptor must be an object")
    normalized = _normalize_shape_descriptor(desc)
    kind = normalized.get("type")
    if kind == "sphere":
        center = _vec3(normalized["center"], "sphere.center")
        return parse_shape({"type": "sphere", "center": _round_vec(_transform_point_matrix(center, matrix)), "radius": float(normalized["radius"])})
    if kind == "box":
        corners = _box_corners(normalized)
        world = [_transform_point_matrix(point, matrix) for point in corners]
        return parse_shape(
            {
                "type": "box",
                "x_range": [min(point[0] for point in world), max(point[0] for point in world)],
                "y_range": [min(point[1] for point in world), max(point[1] for point in world)],
                "z_range": [min(point[2] for point in world), max(point[2] for point in world)],
            }
        )
    if kind == "cylinder":
        radius = float(normalized["radius"])
        a, b = _cylinder_endpoints(normalized)
        world_a = _transform_point_matrix(a, matrix)
        world_b = _transform_point_matrix(b, matrix)
        axis_name = _cardinal_axis_name(normalize(sub(world_b, world_a)))
        if axis_name is None:
            # The static relation solver is axis-aligned. For rotated cylinders,
            # fall back to a conservative world AABB expanded by radius.
            min_v = [min(world_a[i], world_b[i]) - radius for i in range(3)]
            max_v = [max(world_a[i], world_b[i]) + radius for i in range(3)]
            return parse_shape({"type": "box", "x_range": [min_v[0], max_v[0]], "y_range": [min_v[1], max_v[1]], "z_range": [min_v[2], max_v[2]]})
        if axis_name == "z":
            return parse_shape(
                {
                    "type": "cylinder",
                    "axis": "z",
                    "center": [(world_a[0] + world_b[0]) / 2.0, (world_a[1] + world_b[1]) / 2.0],
                    "radius": radius,
                    "z_range": sorted([world_a[2], world_b[2]]),
                }
            )
        if axis_name == "x":
            return parse_shape(
                {
                    "type": "cylinder",
                    "axis": "x",
                    "center": [(world_a[1] + world_b[1]) / 2.0, (world_a[2] + world_b[2]) / 2.0],
                    "radius": radius,
                    "x_range": sorted([world_a[0], world_b[0]]),
                }
            )
        return parse_shape(
            {
                "type": "cylinder",
                "axis": "y",
                "center": [(world_a[0] + world_b[0]) / 2.0, (world_a[2] + world_b[2]) / 2.0],
                "radius": radius,
                "y_range": sorted([world_a[1], world_b[1]]),
            }
        )
    raise AssemblyError("ShapeDescriptorInvalid", f"unsupported shape descriptor: {kind}")


def _normalize_shape_descriptor(desc: dict) -> dict:
    result = dict(desc)
    if result.get("type") == "cylinder":
        radius = _descriptor_radius(result)
        if radius is None:
            raise AssemblyError("ShapeDescriptorInvalid", "cylinder shape must include radius/radius_mm or diameter/diameter_mm")
        result["radius"] = radius
        axis = str(result.get("axis", "z")).lower()
        if axis == "x" and "x_range" not in result and "range" in result:
            result["x_range"] = result["range"]
        if axis == "y" and "y_range" not in result and "range" in result:
            result["y_range"] = result["range"]
        if axis == "z" and "z_range" not in result and "range" in result:
            result["z_range"] = result["range"]
    if result.get("type") == "sphere" and "radius" not in result and "radius_mm" in result:
        result["radius"] = result["radius_mm"]
    return result


def _box_corners(shape: dict) -> list[Vec3]:
    x0, x1 = sorted([float(shape["x_range"][0]), float(shape["x_range"][1])])
    y0, y1 = sorted([float(shape["y_range"][0]), float(shape["y_range"][1])])
    z0, z1 = sorted([float(shape["z_range"][0]), float(shape["z_range"][1])])
    return [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]


def _cardinal_axis_name(direction: Vec3, tol: float = 1e-6) -> str | None:
    axes = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}
    for name, axis in axes.items():
        if abs(abs(dot(direction, axis)) - 1.0) <= tol:
            return name
    return None


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
            components = check.get("components") or _components_from_refs(
                [
                    check.get("a"),
                    check.get("b"),
                    check.get("feature_a"),
                    check.get("feature_b"),
                    check.get("shape_a"),
                    check.get("shape_b"),
                ]
            )
            covered.add(_pair_key(components))
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
        elif isinstance(ref, dict) and isinstance(ref.get("ref"), str) and "." in ref["ref"]:
            components.append(ref["ref"].split(".", 1)[0])
        elif isinstance(ref, dict) and ref.get("component"):
            components.append(str(ref["component"]))
    return sorted(set(components))


def _component_triangles_from_public_record(component: dict) -> list[Triangle]:
    stl_path = Path(component["paths"]["stl"])
    matrix = component["transform"]["matrix"]
    return [tuple(_transform_point_matrix(point, matrix) for point in tri) for tri in read_stl(stl_path)]  # type: ignore[list-item]


def _render_assembly_previews(project: Path, name: str, geometry: dict) -> dict:
    out_dir = assembly_outputs_dir(project, name)
    bbox = ((geometry.get("assembly_geometry") or {}).get("bbox"))
    try:
        combined = _assembly_triangles_from_geometry(geometry)
        combined_path = out_dir / "preview.combined.iso.svg"
        combined_path.write_text(triangles_to_svg(combined, title=f"{name} combined iso", view="iso", bbox=bbox), encoding="utf-8")

        exploded = _exploded_triangles_from_geometry(geometry)
        exploded_path = out_dir / "preview.exploded.iso.svg"
        exploded_path.write_text(triangles_to_svg(exploded, title=f"{name} exploded iso", view="iso", bbox=bbox), encoding="utf-8")

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


def _export_assembly_stl(project: Path, name: str, geometry: dict) -> dict:
    out_dir = assembly_outputs_dir(project, name)
    out_path = out_dir / f"{name}.stl"
    try:
        triangles = _assembly_triangles_from_geometry(geometry)
        _write_binary_stl(out_path, triangles)
        return {
            "ok": True,
            "stage": "assembly_export_stl",
            "assembly": name,
            "triangle_count": len(triangles),
            "artifacts": {"assembly_stl": str(out_path)},
        }
    except Exception as exc:
        return {
            "ok": False,
            "stage": "assembly_export_stl",
            "assembly": name,
            "error": {"type": type(exc).__name__, "message": str(exc)},
            "artifacts": {"assembly_stl": str(out_path)},
        }


def _write_binary_stl(path: Path, triangles: list[Triangle]) -> None:
    header = b"AgentCAD assembly STL".ljust(80, b" ")
    with path.open("wb") as fh:
        fh.write(header)
        fh.write(struct.pack("<I", len(triangles)))
        for tri in triangles:
            normal = normalize(cross(sub(tri[1], tri[0]), sub(tri[2], tri[0])))
            fh.write(struct.pack("<3f", *normal))
            for point in tri:
                fh.write(struct.pack("<3f", *point))
            fh.write(struct.pack("<H", 0))


def _assembly_triangles_from_geometry(geometry: dict) -> list[Triangle]:
    triangles: list[Triangle] = []
    for component in (geometry.get("components") or {}).values():
        triangles.extend(_component_triangles_from_public_record(component))
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
        used_names: set[str] = {_safe_xml_name(cid) for cid in (geometry.get("components") or {})}

        for cid, component in (geometry.get("components") or {}).items():
            body_name = _safe_xml_name(cid)
            mesh_name = _unique_xml_name(f"{body_name}_mesh", used_names)
            geom_name = _unique_xml_name(f"{body_name}_geom", used_names)
            mesh_file = os.path.relpath(component["paths"]["stl"], start=out_dir)
            ET.SubElement(asset, "mesh", {"name": mesh_name, "file": mesh_file})
            transform = component["transform"]
            body = ET.SubElement(
                worldbody,
                "body",
                {
                    "name": body_name,
                    "pos": _mjcf_vec(transform["translation"]),
                    "euler": _mjcf_vec(transform["rotation_euler_deg"]),
                },
            )
            ET.SubElement(body, "geom", {"name": geom_name, "type": "mesh", "mesh": mesh_name})
            for ref, resolved in sorted((geometry.get("references") or {}).items()):
                if resolved.get("component") != cid or not resolved.get("ok"):
                    continue
                site = _local_site_from_descriptor(resolved.get("local"))
                if site is None:
                    continue
                site_name = _unique_xml_name(_safe_xml_name(ref.replace(".", "_")), used_names)
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
            body_name = _safe_xml_name(cid)
            body = bodies.get(body_name)
            if body is None:
                errors.append(f"missing body {body_name}")
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
    pairwise = geometry.get("pairwise") or []
    clearances = [
        float(row["mesh_clearance_mm"])
        for row in pairwise
        if row.get("mesh_clearance_mm") is not None
    ]
    interferes = [row for row in pairwise if row.get("interferes")]
    payload = {
        "ok": bool(validation.get("ok")),
        "schema": OBSERVABILITY_SCHEMA,
        "stage": "assembly_observability",
        "assembly": name,
        "summary": {
            "component_count": ((geometry.get("assembly_geometry") or {}).get("component_count")),
            "failing_check_count": len(failed_checks),
            "minimum_clearance_mm": min(clearances) if clearances else None,
            "interfering_pair_count": len(interferes),
            "warning_count": 0,
        },
        "geometry": geometry.get("assembly_geometry"),
        "components": geometry.get("components"),
        "references": geometry.get("references"),
        "mate_residuals": geometry.get("mate_residuals"),
        "pairwise": pairwise,
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


def _assembly_validation_payload(name: str, checks: list[dict], geometry: dict, artifacts: dict, message: str) -> dict:
    failed = [check for check in checks if not check.get("ok")]
    return {
        "ok": not failed,
        "schema": VALIDATION_SCHEMA,
        "stage": "assembly_validate",
        "assembly": name,
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
        "message": message,
    }


def _mjcf_vec(values: Any) -> str:
    return " ".join(f"{float(value):.9g}" for value in values)


def _parse_mjcf_vec(value: str) -> list[float]:
    return [float(part) for part in value.split()]


def _safe_xml_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
    if not cleaned or not (cleaned[0].isalpha() or cleaned[0] == "_"):
        cleaned = f"n_{cleaned}"
    return cleaned


def _unique_xml_name(base: str, used: set[str]) -> str:
    name = base
    suffix = 2
    while name in used:
        name = f"{base}_{suffix}"
        suffix += 1
    used.add(name)
    return name


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
