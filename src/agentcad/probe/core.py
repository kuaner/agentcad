from __future__ import annotations

from pathlib import Path

from ..contract.evidence import evaluate_feature_evidence_matrix_dict
from ..jsonio import read_json, write_json
from ..workspace import model_dir, outputs_dir
from .execution import run_probe_plan
from .planner import plan_probe_points


def plan_probes(project: Path, name: str, *, run: bool = False) -> dict:
    """Suggest high-value probe/render commands from contract and artifacts."""
    mdir = model_dir(project, name)
    design = read_json(mdir / "design.json", default=None)
    if not isinstance(design, dict):
        return {
            "ok": False,
            "stage": "probe-plan",
            "model": name,
            "suggested_probes": [],
            "error": {
                "type": "DesignNotFound",
                "message": f"design.json not found for model '{name}'",
            },
        }

    out_dir = outputs_dir(project, name)
    params = read_json(mdir / "params.json", default={}) or {}
    metadata = read_json(mdir / "metadata.json", default={}) or {}
    geometry = read_json(out_dir / "geometry.json", default={}) or {}
    validation = read_json(out_dir / "validation.json", default={}) or {}
    observability = read_json(out_dir / "observability.json", default={}) or {}
    matrix = evaluate_feature_evidence_matrix_dict(design)
    suggested = plan_probe_points(
        name,
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
        "model": name,
        "suggested_probes": suggested,
        "feature_evidence_matrix": matrix,
    }
    if run:
        execution = run_probe_plan(project, name, suggested)
        probes_path = out_dir / "probes.json"
        payload["execution"] = execution
        payload["artifacts"] = {"probes": str(probes_path)}
        payload["ok"] = bool(execution.get("ok"))
        write_json(probes_path, payload)
    return payload
