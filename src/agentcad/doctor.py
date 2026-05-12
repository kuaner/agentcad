"""Doctor command: inspect workspace state and report workflow gaps.

``agentcad doctor`` examines the current artifact state for a model (or
assembly) and produces a structured diagnostic report with severity-graded
findings and recommended next commands. Agents can use this to resume an
interrupted workflow without manually inspecting files.

State machine:
  missing_design → needs_precheck → needs_build → needs_validation
  → needs_review → ready_for_delivery → blocked (if any finding is blocking)

Output schema:
  {
    "ok": bool,
    "stage": "doctor",
    "model": str,
    "state": str,
    "findings": [{id, severity, message, next_command, artifact}],
    "next_command": str | null
  }
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .jsonio import read_json
from .workspace import model_dir, outputs_dir

# ── Data structures ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DoctorFinding:
    id: str
    severity: str  # "info" | "warning" | "blocking"
    message: str
    next_command: str | None = None
    artifact: str | None = None


WORKFLOW_STATES = (
    "missing_design",
    "needs_precheck",
    "needs_build",
    "needs_validation",
    "needs_review",
    "ready_for_delivery",
    "blocked",
)


# ── Public API ────────────────────────────────────────────────────────────────


def run_model_doctor(project: Path, name: str, variant: str | None = None) -> dict:
    """Inspect model artifacts and report workflow gaps."""
    mdir = model_dir(project, name)
    out_dir = outputs_dir(project, name)
    artifacts = _model_artifact_state(mdir, out_dir)
    findings: list[DoctorFinding] = []
    for rule in MODEL_DOCTOR_RULES:
        finding = rule(project, name, variant, artifacts)
        if finding is not None:
            findings.append(finding)

    state = _determine_state(findings, artifacts)
    blocking = [f for f in findings if f.severity == "blocking"]
    next_cmd = None
    if blocking:
        next_cmd = blocking[0].next_command
    elif findings:
        # First non-blocking finding's command.
        for f in findings:
            if f.next_command:
                next_cmd = f.next_command
                break

    ok = state == "ready_for_delivery" or (state != "blocked" and not blocking)
    return {
        "ok": ok,
        "stage": "doctor",
        "model": name,
        "state": state,
        "findings": [_finding_to_dict(f) for f in findings],
        "next_command": next_cmd,
        "artifacts": artifacts,
    }


# ── Artifact state ────────────────────────────────────────────────────────


def _model_artifact_state(mdir: Path, out_dir: Path) -> dict[str, Any]:
    """Check which artifacts exist and their timestamps."""
    design = mdir / "design.json"
    params = mdir / "params.json"
    part_py = mdir / "part.py"
    metadata = mdir / "metadata.json"
    build_json = out_dir / "build.json"
    geometry_json = out_dir / "geometry.json"
    validation_json = out_dir / "validation.json"
    precheck_json = out_dir / "precheck.json"
    review_json = out_dir / "review.json"
    preview_html = out_dir / "preview.html"

    state = {
        "design_json": design.exists(),
        "params_json": params.exists(),
        "part_py": part_py.exists(),
        "metadata_json": metadata.exists(),
        "build_json": build_json.exists(),
        "geometry_json": geometry_json.exists(),
        "validation_json": validation_json.exists(),
        "precheck_json": precheck_json.exists(),
        "review_json": review_json.exists(),
        "preview_html": preview_html.exists(),
        "preview_svgs": len(list(out_dir.glob("preview.*.svg"))) > 0,
        "stl": (out_dir / f"{mdir.name}.stl").exists(),
        "step": (out_dir / f"{mdir.name}.step").exists(),
    }

    # Freshness checks: source newer than build?
    if part_py.exists() and build_json.exists():
        state["source_newer_than_build"] = part_py.stat().st_mtime > build_json.stat().st_mtime
    else:
        state["source_newer_than_build"] = False

    if params.exists() and build_json.exists():
        state["params_newer_than_build"] = params.stat().st_mtime > build_json.stat().st_mtime
    else:
        state["params_newer_than_build"] = False

    # Validation older than build?
    if validation_json.exists() and build_json.exists():
        state["validation_older_than_build"] = validation_json.stat().st_mtime < build_json.stat().st_mtime
    else:
        state["validation_older_than_build"] = False

    # Validation result.
    if validation_json.exists():
        val = read_json(validation_json, default={})
        state["validation_ok"] = val.get("ok")
    else:
        state["validation_ok"] = None

    # Review result.
    if review_json.exists():
        rev = read_json(review_json, default={})
        state["review_ok"] = rev.get("ok")
    else:
        state["review_ok"] = None

    return state


# ── Diagnostic rules ────────────────────────────────────────────────────────


def _rule_design_missing(project: Path, name: str, variant: str | None, artifacts: dict) -> DoctorFinding | None:
    if not artifacts.get("design_json"):
        return DoctorFinding(
            "design_missing", "blocking",
            "design.json is missing — cannot proceed without a design contract",
            next_command="agentcad new <model> or create design.json manually",
        )
    return None


def _rule_precheck_missing(project: Path, name: str, variant: str | None, artifacts: dict) -> DoctorFinding | None:
    if artifacts.get("design_json") and not artifacts.get("precheck_json"):
        return DoctorFinding(
            "precheck_missing", "warning",
            "precheck.json is missing — run precheck before writing part.py",
            next_command=f"agentcad precheck {name}",
        )
    return None


def _rule_build_missing(project: Path, name: str, variant: str | None, artifacts: dict) -> DoctorFinding | None:
    if not artifacts.get("build_json") or not artifacts.get("stl"):
        return DoctorFinding(
            "build_missing", "blocking",
            "STL/STEP or build.json is missing — model has not been built",
            next_command=f"agentcad build {name}",
        )
    return None


def _rule_source_newer(project: Path, name: str, variant: str | None, artifacts: dict) -> DoctorFinding | None:
    if artifacts.get("source_newer_than_build") or artifacts.get("params_newer_than_build"):
        return DoctorFinding(
            "source_newer_than_build", "blocking",
            "part.py or params.json is newer than build.json — build is stale",
            next_command=f"agentcad build {name}",
        )
    return None


def _rule_validation_missing(project: Path, name: str, variant: str | None, artifacts: dict) -> DoctorFinding | None:
    if artifacts.get("build_json") and not artifacts.get("validation_json"):
        return DoctorFinding(
            "validation_missing", "blocking",
            "validation.json is missing — model has not been validated",
            next_command=f"agentcad validate {name}",
        )
    return None


def _rule_validation_failed(project: Path, name: str, variant: str | None, artifacts: dict) -> DoctorFinding | None:
    val_ok = artifacts.get("validation_ok")
    if val_ok is False:
        return DoctorFinding(
            "validation_failed", "blocking",
            "validation.json exists but ok=false — validation failed",
            next_command=f"agentcad validate {name}",
        )
    return None


def _rule_validation_stale(project: Path, name: str, variant: str | None, artifacts: dict) -> DoctorFinding | None:
    if artifacts.get("validation_older_than_build") and artifacts.get("validation_ok") is not None:
        return DoctorFinding(
            "validation_stale", "warning",
            "validation.json is older than build.json — re-validate after rebuild",
            next_command=f"agentcad validate {name}",
        )
    return None


def _rule_review_missing(project: Path, name: str, variant: str | None, artifacts: dict) -> DoctorFinding | None:
    if artifacts.get("validation_ok") is True and not artifacts.get("review_json"):
        return DoctorFinding(
            "review_missing", "warning",
            "validation passed but review.json is missing — run review before delivery",
            next_command=f"agentcad review {name}",
        )
    return None


def _rule_preview_missing(project: Path, name: str, variant: str | None, artifacts: dict) -> DoctorFinding | None:
    if artifacts.get("validation_ok") is True and not artifacts.get("preview_html"):
        return DoctorFinding(
            "preview_missing", "warning",
            "preview.html is missing — interactive preview not available",
            next_command=f"agentcad preview {name}",
        )
    return None


MODEL_DOCTOR_RULES = [
    _rule_design_missing,
    _rule_precheck_missing,
    _rule_build_missing,
    _rule_source_newer,
    _rule_validation_missing,
    _rule_validation_failed,
    _rule_validation_stale,
    _rule_review_missing,
    _rule_preview_missing,
]


# ── State determination ────────────────────────────────────────────────────


def _determine_state(findings: list[DoctorFinding], artifacts: dict) -> str:
    """Determine the workflow state based on findings and artifact presence."""
    blocking = [f for f in findings if f.severity == "blocking"]
    if blocking:
        return "blocked"

    if not artifacts.get("design_json"):
        return "missing_design"
    if not artifacts.get("precheck_json"):
        return "needs_precheck"
    if not artifacts.get("build_json") or not artifacts.get("stl"):
        return "needs_build"
    if not artifacts.get("validation_json") or artifacts.get("validation_ok") is False:
        return "needs_validation"
    if not artifacts.get("review_json") or artifacts.get("review_ok") is False:
        return "needs_review"
    return "ready_for_delivery"


# ── Helpers ────────────────────────────────────────────────────────────────


def _finding_to_dict(f: DoctorFinding) -> dict[str, Any]:
    d: dict[str, Any] = {
        "id": f.id,
        "severity": f.severity,
        "message": f.message,
    }
    if f.next_command:
        d["next_command"] = f.next_command
    if f.artifact:
        d["artifact"] = f.artifact
    return d