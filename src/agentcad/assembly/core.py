from __future__ import annotations

from pathlib import Path

from ..jsonio import read_json, write_json
from ..workspace import normalize_model_name
from .artifacts import (
    _export_assembly_stl,
    _export_mjcf,
    _mjcf_consistency_check,
    _render_assembly_previews,
    _transform_consistency_check,
)
from .checks import (
    _assembly_interface_contract_checks,
    _component_pair_classification_checks,
    _evaluate_user_checks,
    _fit_coverage_checks,
    _fresh_component_checks,
    _mate_checks,
)
from .components import _load_components, _public_component_record, _validate_component_ids
from .mates import _evaluate_mates
from .metadata_checks import _evaluate_metadata_geometry, _metadata_schema_checks
from .mesh import _global_bbox, _measure_pairwise
from .paths import assemblies_dir, assembly_dir, assembly_outputs_dir
from .references import _collect_references, _resolve_references
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
