from __future__ import annotations

import math
import os
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from ..render import triangles_to_svg
from ..stl import Triangle, Vec3, cross, length, normalize, read_stl, sub
from .naming import _safe_xml_name, _unique_xml_name
from .paths import assembly_outputs_dir
from .references import _cylinder_endpoints, _is_axis_descriptor, _is_cylinder_descriptor
from .transform import _mul, _round_vec, _transform_point_matrix, _translate_triangle, _vec3
from .types import EPS


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


def _mjcf_vec(values: Any) -> str:
    return " ".join(f"{float(value):.9g}" for value in values)


def _parse_mjcf_vec(value: str) -> list[float]:
    return [float(part) for part in value.split()]


def _vectors_close(a: list[float], b: list[float], tol: float = 1e-6) -> bool:
    return len(a) == len(b) and all(abs(float(a[i]) - float(b[i])) <= tol for i in range(len(a)))
