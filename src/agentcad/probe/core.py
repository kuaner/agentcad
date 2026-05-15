from __future__ import annotations

from pathlib import Path

from ..contract.evidence import evaluate_feature_evidence_matrix_dict
from ..jsonio import read_json, write_json
from ..workspace import format_model_target, model_dir, outputs_dir_for_variant, parse_model_target, variant_params_path
from .execution import run_probe_plan
from .planner import plan_probe_points


def plan_probes(project: Path, name: str, *, run: bool = False) -> dict:
    """Suggest high-value probe/render commands from contract and artifacts."""
    model_name, variant = parse_model_target(name)
    target = format_model_target(model_name, variant)
    mdir = model_dir(project, model_name)
    design = read_json(mdir / "design.json", default=None)
    if not isinstance(design, dict):
        return {
            "ok": False,
            "stage": "probe-plan",
            "model": model_name,
            "variant": variant,
            "suggested_probes": [],
            "error": {
                "type": "DesignNotFound",
                "message": f"design.json not found for model '{model_name}'",
            },
        }

    out_dir = outputs_dir_for_variant(project, model_name, variant)
    params_path = variant_params_path(project, model_name, variant) if variant else mdir / "params.json"
    params = read_json(params_path, default={}) or {}
    metadata = read_json(out_dir / "metadata.json", default=None)
    if metadata is None:
        metadata = read_json(mdir / "metadata.json", default={}) or {}
    geometry = read_json(out_dir / "geometry.json", default={}) or {}
    validation = read_json(out_dir / "validation.json", default={}) or {}
    observability = read_json(out_dir / "observability.json", default={}) or {}
    matrix = evaluate_feature_evidence_matrix_dict(design)
    suggested = plan_probe_points(
        target,
        design,
        params=params,
        metadata=metadata,
        geometry=geometry,
        validation=validation,
        observability=observability,
        feature_evidence_matrix=matrix,
    )
    payload = {
        "ok": True,
        "stage": "probe-plan",
        "model": model_name,
        "variant": variant,
        "target": target,
        "suggested_probes": suggested,
        "feature_evidence_matrix": matrix,
    }
    if run:
        execution = run_probe_plan(project, target, suggested)
        probes_path = out_dir / "probes.json"
        payload["execution"] = execution
        payload["artifacts"] = {"probes": str(probes_path)}
        payload["ok"] = bool(execution.get("ok"))
        write_json(probes_path, payload)
    return payload
