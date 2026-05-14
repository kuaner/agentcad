from __future__ import annotations

from pathlib import Path

from ..jsonio import read_json
from ..metadata import validate_part_metadata_dict
from ..runner import build_model
from ..stl import mesh_report, read_stl
from ..workspace import model_dir, outputs_dir
from .naming import _safe_xml_name
from .transform import _parse_transform, _round_matrix, _round_vec, _transform_triangle
from .types import AssemblyError, Transform


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

        local_triangles: list = []
        world_triangles: list = []
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
            "paths": {
                "model_dir": str(model_dir(project, model)),
                "build": str(out_dir / "build.json"),
                "stl": str(stl_path),
                "step": str(step_path),
                "metadata": str(metadata_path),
            },
            "build": build,
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
            raise AssemblyError(
                "ComponentIdCollision",
                f"component ids {previous!r} and {cid!r} collapse to the same MJCF name {safe!r}",
            )
        safe_names[safe] = cid


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
