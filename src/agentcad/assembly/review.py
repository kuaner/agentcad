from __future__ import annotations

from pathlib import Path

from ..jsonio import read_json, write_json
from ..workspace import normalize_model_name
from .paths import assembly_dir, assembly_outputs_dir


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
        for key in (
            "mjcf",
            "assembly_stl",
            "preview_combined_iso",
            "preview_exploded_iso",
            "preview_page",
            "geometry",
        ):
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
                check
                for check in validation.get("checks", [])
                if str(check.get("name", "")).startswith("assembly_interface:")
            ]
            checks.append(
                {
                    "name": "assembly_interfaces_validated",
                    "type": "assembly_interface_contract",
                    "ok": bool(interface_checks) and all(check.get("ok") for check in interface_checks),
                    "expected_interfaces": (
                        len(interface_contracts)
                        if isinstance(interface_contracts, list)
                        else len(interface_contracts.keys())
                    ),
                    "validated_interfaces": len(interface_checks),
                    "failed": [check.get("name") for check in interface_checks if not check.get("ok")],
                }
            )

    failed = [check for check in checks if not check.get("ok")]
    payload = {
        "ok": not failed,
        "stage": "assembly_review",
        "assembly": safe,
        "checks": checks,
        "summary": {"checks": len(checks), "failed": len(failed)},
        "artifacts": {
            "review": str(review_path),
            "validation": str(validation_path),
            "observability": str(observability_path),
        },
        "message": "assembly review passed" if not failed else "assembly review blocked",
    }
    write_json(review_path, payload)
    return payload
