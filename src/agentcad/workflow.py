from __future__ import annotations

from pathlib import Path
from typing import Callable

from .jsonio import write_json
from .precheck import precheck_model
from .preview import check_preview_page, write_model_preview
from .probe import plan_probes
from .review import review_model
from .suggest import suggest_checks
from .validate import deliver_model, validate_model
from .workspace import format_model_target, outputs_dir_for_variant, parse_model_target


def run_workflow(project: Path, target: str) -> dict:
    """Run the final model delivery gates and write outputs/workflow.json."""
    model, variant = parse_model_target(target)
    display = format_model_target(model, variant)
    out_dir = outputs_dir_for_variant(project, model, variant)
    out_dir.mkdir(parents=True, exist_ok=True)
    workflow_path = out_dir / "workflow.json"

    steps: list[dict] = []
    gates: dict[str, dict] = {}
    artifacts: dict[str, str] = {"workflow": str(workflow_path)}

    def finish(ok: bool, next_command: str | None = None) -> dict:
        payload = {
            "ok": ok,
            "stage": "workflow",
            "model": model,
            "variant": variant,
            "target": display,
            "steps": steps,
            "gates": gates,
            "artifacts": artifacts,
            "next_command": next_command,
        }
        write_json(workflow_path, payload)
        return payload

    suggest = _run_step("suggest-checks", lambda: suggest_checks(project, display))
    quality = suggest.get("suggestion_quality") or {}
    suggestion_count = len(suggest.get("suggestions") or [])
    placeholder_count = int(quality.get("placeholder_count") or 0)
    gates["no_open_suggestions"] = {"ok": bool(suggest.get("ok")) and suggestion_count == 0, "count": suggestion_count}
    gates["no_placeholders"] = {"ok": bool(suggest.get("ok")) and placeholder_count == 0, "count": placeholder_count}
    suggest_ok = bool(suggest.get("ok")) and gates["no_open_suggestions"]["ok"] and gates["no_placeholders"]["ok"]
    steps.append(_step("suggest-checks", suggest_ok, suggest))
    if not suggest_ok:
        _skip_remaining(steps, ["precheck", "validate", "preview-check", "probe-plan-run", "review", "deliver"])
        next_cmd = f"agentcad suggest-checks {display}"
        if suggestion_count and placeholder_count == 0 and not variant:
            next_cmd = f"{next_cmd} --apply"
        return finish(False, next_cmd)

    precheck = _run_step("precheck", lambda: precheck_model(project, model))
    _record_artifacts(artifacts, precheck)
    gates["precheck"] = {"ok": bool(precheck.get("ok"))}
    steps.append(_step("precheck", bool(precheck.get("ok")), precheck))
    if not precheck.get("ok"):
        _skip_remaining(steps, ["validate", "preview-check", "probe-plan-run", "review", "deliver"])
        return finish(False, f"agentcad precheck {model}")

    validation = _run_step("validate", lambda: validate_model(project, model, variant=variant))
    _record_artifacts(artifacts, validation)
    gates["validate"] = {"ok": bool(validation.get("ok"))}
    steps.append(_step("validate", bool(validation.get("ok")), validation))
    if not validation.get("ok"):
        _skip_remaining(steps, ["preview-check", "probe-plan-run", "review", "deliver"])
        return finish(False, f"agentcad validate {display}")

    preview = _run_step("preview-check", lambda: _check_model_preview(project, model, variant))
    _record_artifacts(artifacts, preview)
    gates["preview_health"] = {"ok": bool(preview.get("ok")), "broken_assets": preview.get("broken_assets") or []}
    steps.append(_step("preview-check", bool(preview.get("ok")), preview))
    if not preview.get("ok"):
        _skip_remaining(steps, ["probe-plan-run", "review", "deliver"])
        return finish(False, f"agentcad preview-check {display} --kind model")

    probes = _run_step("probe-plan-run", lambda: plan_probes(project, display, run=True))
    _record_artifacts(artifacts, probes)
    gates["probe"] = {"ok": bool(probes.get("ok"))}
    steps.append(_step("probe-plan-run", bool(probes.get("ok")), probes))
    if not probes.get("ok"):
        _skip_remaining(steps, ["review", "deliver"])
        return finish(False, f"agentcad probe {display} --plan --run")

    review = _run_step("review", lambda: review_model(project, model, variant=variant))
    _record_artifacts(artifacts, review)
    gates["review"] = {"ok": bool(review.get("ok"))}
    steps.append(_step("review", bool(review.get("ok")), review))
    if not review.get("ok"):
        _skip_remaining(steps, ["deliver"])
        return finish(False, f"agentcad review {display}")

    deliver = _run_step("deliver", lambda: deliver_model(project, model, run_validation=False, variant=variant))
    _record_artifacts(artifacts, deliver)
    gates["deliver"] = {"ok": bool(deliver.get("ok"))}
    steps.append(_step("deliver", bool(deliver.get("ok")), deliver))
    if not deliver.get("ok"):
        return finish(False, f"agentcad deliver {display} --no-validate")

    return finish(True, None)


def _check_model_preview(project: Path, model: str, variant: str | None) -> dict:
    preview = write_model_preview(project, model, variant=variant)
    if not preview.get("ok"):
        return {**preview, "stage": "preview-check"}
    return check_preview_page(Path((preview.get("artifacts") or {})["preview_page"]))


def _run_step(name: str, fn: Callable[[], dict]) -> dict:
    try:
        return fn()
    except Exception as exc:
        return {"ok": False, "stage": name, "error": {"type": type(exc).__name__, "message": str(exc)}}


def _step(name: str, ok: bool, payload: dict) -> dict:
    row = {
        "name": name,
        "ok": bool(ok),
        "payload_ok": bool(payload.get("ok")),
        "stage": payload.get("stage"),
    }
    if payload.get("error"):
        row["error"] = payload["error"]
    if payload.get("artifacts"):
        row["artifacts"] = payload["artifacts"]
    if name == "suggest-checks":
        quality = payload.get("suggestion_quality") or {}
        row["suggestion_count"] = len(payload.get("suggestions") or [])
        row["placeholder_count"] = quality.get("placeholder_count", 0)
        row["patch_count"] = len(payload.get("patches") or [])
    if name == "validate":
        checks = payload.get("checks") or []
        row["check_count"] = len(checks)
        row["failed_checks"] = [check.get("name") for check in checks if not check.get("ok")]
    if name == "preview-check":
        row["assets_checked"] = payload.get("assets_checked", 0)
        row["broken_assets"] = payload.get("broken_assets") or []
    if name == "probe-plan-run":
        execution = payload.get("execution") or {}
        row["probe_count"] = execution.get("count", 0)
        row["failed_probe_count"] = execution.get("failed", 0)
    if name == "review":
        checklist = payload.get("checklist") or []
        row["checklist_count"] = len(checklist)
        row["failed_items"] = [item.get("id") for item in checklist if not item.get("ok")]
    return row


def _skip_remaining(steps: list[dict], names: list[str]) -> None:
    for name in names:
        steps.append({"name": name, "ok": False, "skipped": True})


def _record_artifacts(artifacts: dict[str, str], payload: dict) -> None:
    for key, value in (payload.get("artifacts") or {}).items():
        if isinstance(value, str):
            artifacts[key] = value
