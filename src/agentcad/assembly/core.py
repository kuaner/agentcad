from __future__ import annotations

from pathlib import Path
from typing import Any

from ..geometry import min_clearance_3d, parse_shape
from ..jsonio import read_json, write_json
from ..section import AXIS_X, AXIS_Y, AXIS_Z, analyze_section_segments, section_segments
from ..workspace import normalize_model_name
from .artifacts import (
    _component_triangles_from_public_record,
    _export_assembly_stl,
    _export_mjcf,
    _mjcf_consistency_check,
    _render_assembly_previews,
    _transform_consistency_check,
)
from .components import _load_components, _public_component_record, _validate_component_ids
from .mates import _angle_deg, _axis_from_ref, _evaluate_mates, _point_axis_distance, _required_float
from .metadata_checks import _evaluate_metadata_geometry, _metadata_schema_checks
from .mesh import _global_bbox, _measure_pairwise
from .paths import assemblies_dir, assembly_dir, assembly_outputs_dir
from .references import (
    _collect_references,
    _components_from_refs,
    _descriptor_radius,
    _is_cylinder_descriptor,
    _normalize_shape_descriptor,
    _resolve_references,
    _transform_shape_descriptor,
)
from .types import (
    ASSEMBLY_SCHEMA,
    GEOMETRY_SCHEMA,
    OBSERVABILITY_SCHEMA,
    VALIDATION_SCHEMA,
    AssemblyError,
)


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

        from ..preview import write_assembly_preview

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


def _failure(assembly: str, stage: str, error_type: str, message: str) -> dict:
    return {
        "ok": False,
        "stage": stage,
        "assembly": assembly,
        "error": {"type": error_type, "message": message},
    }
