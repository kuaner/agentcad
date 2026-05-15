from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from agentcad.cli import main
from agentcad.workflow import run_workflow
from agentcad.workspace import init_workspace, new_model, model_dir


ROOT = Path(__file__).resolve().parents[1]


def _copy_proof_workspace(tmp_path: Path) -> Path:
    source = ROOT / "examples" / "workflow-proof-wall-hook"
    target = tmp_path / "workflow-proof-wall-hook"
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("outputs"))
    return target


def test_workflow_proof_fixture_runs_end_to_end(tmp_path, monkeypatch):
    project = _copy_proof_workspace(tmp_path)
    monkeypatch.chdir(project)

    result = main(["workflow", "edge_access_bracket"])
    workflow_path = project / "models" / "edge_access_bracket" / "outputs" / "workflow.json"
    payload = json.loads(workflow_path.read_text(encoding="utf-8"))

    assert result == 0
    assert payload["ok"] is True
    assert payload["gates"]["preview_health"]["ok"] is True
    assert payload["next_command"] is None


def test_workflow_blocks_on_open_suggestions_and_marks_dependents_skipped(tmp_path):
    init_workspace(tmp_path)
    new_model(tmp_path, "needs_checks")
    mdir = model_dir(tmp_path, "needs_checks")
    (mdir / "design.json").write_text(
        json.dumps({"features": [{"id": "body", "checks": []}], "checks": []}),
        encoding="utf-8",
    )
    (mdir / "params.json").write_text(json.dumps({"length": 20, "depth": 10, "height": 5}), encoding="utf-8")

    result = run_workflow(tmp_path, "needs_checks")

    assert result["ok"] is False
    assert result["gates"]["no_open_suggestions"]["ok"] is False
    assert result["next_command"] == "agentcad suggest-checks needs_checks"
    assert [step["name"] for step in result["steps"][:2]] == ["suggest-checks", "precheck"]
    assert result["steps"][1]["skipped"] is True


def test_workflow_precheck_failure_sets_next_command(monkeypatch, tmp_path):
    init_workspace(tmp_path)
    new_model(tmp_path, "bad_contract")

    import agentcad.workflow as workflow_mod

    monkeypatch.setattr(workflow_mod, "suggest_checks", lambda *a, **kw: {
        "ok": True,
        "suggestions": [],
        "patches": [],
        "suggestion_quality": {"placeholder_count": 0},
    })
    monkeypatch.setattr(workflow_mod, "precheck_model", lambda *a, **kw: {
        "ok": False,
        "stage": "precheck",
        "error": {"type": "ContractFailed", "message": "bad"},
    })

    result = run_workflow(tmp_path, "bad_contract")

    assert result["ok"] is False
    assert result["gates"]["precheck"]["ok"] is False
    assert result["next_command"] == "agentcad precheck bad_contract"
    assert any(step["name"] == "validate" and step["skipped"] for step in result["steps"])


def test_workflow_passes_variant_through_model_steps(monkeypatch, tmp_path):
    init_workspace(tmp_path)
    new_model(tmp_path, "variant_box")

    import agentcad.workflow as workflow_mod

    calls = {}

    def fake_suggest(project, target):
        calls["suggest"] = target
        return {"ok": True, "suggestions": [], "patches": [], "suggestion_quality": {"placeholder_count": 0}}

    def fake_precheck(project, model):
        calls["precheck"] = model
        return {"ok": True, "artifacts": {"precheck": "precheck.json"}}

    def fake_validate(project, model, variant=None):
        calls["validate"] = (model, variant)
        return {"ok": True, "checks": [], "artifacts": {"validation": "validation.json"}}

    def fake_preview(project, model, variant=None):
        calls["preview"] = (model, variant)
        return {"ok": True, "assets_checked": 1, "broken_assets": []}

    def fake_probe(project, target, run=False):
        calls["probe"] = (target, run)
        return {"ok": True, "execution": {"count": 0, "failed": 0}, "artifacts": {"probes": "probes.json"}}

    def fake_review(project, model, variant=None):
        calls["review"] = (model, variant)
        return {"ok": True, "checklist": [], "artifacts": {"review": "review.json"}}

    def fake_deliver(project, model, run_validation=True, variant=None):
        calls["deliver"] = (model, variant, run_validation)
        return {"ok": True, "artifacts": {"deliverable": "deliverable.json"}}

    monkeypatch.setattr(workflow_mod, "suggest_checks", fake_suggest)
    monkeypatch.setattr(workflow_mod, "precheck_model", fake_precheck)
    monkeypatch.setattr(workflow_mod, "validate_model", fake_validate)
    monkeypatch.setattr(workflow_mod, "_check_model_preview", fake_preview)
    monkeypatch.setattr(workflow_mod, "plan_probes", fake_probe)
    monkeypatch.setattr(workflow_mod, "review_model", fake_review)
    monkeypatch.setattr(workflow_mod, "deliver_model", fake_deliver)

    result = run_workflow(tmp_path, "variant_box:small")

    assert result["ok"] is True
    assert calls["suggest"] == "variant_box:small"
    assert calls["precheck"] == "variant_box"
    assert calls["validate"] == ("variant_box", "small")
    assert calls["preview"] == ("variant_box", "small")
    assert calls["probe"] == ("variant_box:small", True)
    assert calls["review"] == ("variant_box", "small")
    assert calls["deliver"] == ("variant_box", "small", False)
