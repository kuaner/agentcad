from __future__ import annotations

from typing import Any

from ..geometry import min_clearance_3d, parse_shape
from ..section import AXIS_X, AXIS_Y, AXIS_Z, analyze_section_segments, section_segments
from .artifacts import _component_triangles_from_public_record
from .mates import _angle_deg, _axis_from_ref, _point_axis_distance, _required_float
from .references import (
    _components_from_refs,
    _descriptor_radius,
    _is_cylinder_descriptor,
    _normalize_shape_descriptor,
    _transform_shape_descriptor,
)
from .types import AssemblyError


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
        return [
            {
                "name": "assembly_interfaces_schema",
                "type": "assembly_interface_contract",
                "ok": False,
                "error": {"type": "InterfacesInvalid", "message": "assembly interfaces must be a list or object"},
            }
        ]
    refs = geometry.get("references") or {}
    for index, interface in enumerate(interfaces):
        if not isinstance(interface, dict):
            checks.append(
                {
                    "name": f"assembly_interface:{index}",
                    "type": "assembly_interface_contract",
                    "ok": False,
                    "error": {"type": "InterfaceInvalid", "message": "interface must be an object"},
                }
            )
            continue
        iface_type = str(interface.get("type") or "")
        name = str(interface.get("id") or f"interface_{index}")
        if iface_type in ("cylindrical_mate", "cylindrical_fit", "coaxial_fit"):
            checks.append(_eval_assembly_cylindrical_interface(name, interface, refs, geometry))
        else:
            checks.append(
                {
                    "name": f"assembly_interface:{name}",
                    "type": "assembly_interface_contract",
                    "ok": False,
                    "interface_type": iface_type,
                    "error": {"type": "UnsupportedAssemblyInterfaceType", "message": f"unsupported interface type: {iface_type}"},
                }
            )
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
        "error": None
        if ok
        else {"type": "AssemblyInterfaceMismatch", "message": "cylindrical interface is eccentric, angled, or lacks required radial clearance"},
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
    pair = _pair_key(
        check.get("components")
        or _components_from_refs([check.get("a"), check.get("b"), check.get("feature_a"), check.get("feature_b"), check.get("shape_a"), check.get("shape_b")])
    )
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
