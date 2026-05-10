from __future__ import annotations

import json
from pathlib import Path

from agentcad.diff import archive_validation, diff_model, diff_validations
from agentcad.workspace import init_workspace, new_model
from agentcad.runner import build_model
from agentcad.validate import validate_model


def test_archive_validation_creates_history(tmp_path):
    init_workspace(tmp_path)
    new_model(tmp_path, "archive_test")
    d = tmp_path / "models" / "archive_test" / "outputs"
    d.mkdir(parents=True, exist_ok=True)
    (d / "validation.json").write_text(json.dumps({"ok": True, "checks": []}))

    result = archive_validation(d)
    assert result is not None
    assert result.exists()
    assert (d / "validation-history").is_dir()


def test_archive_validation_skips_missing(tmp_path):
    result = archive_validation(tmp_path)
    assert result is None


def test_diff_identical_runs():
    payload = {"ok": True, "checks": [{"name": "a", "type": "t", "ok": True}]}
    result = diff_validations(payload, payload)
    assert result["ok"] is True
    assert result["checks_fixed"] == []
    assert result["checks_regressed"] == []
    assert result["checks_stable_pass"] == [{"name": "a", "type": "t"}]


def test_diff_detects_regression():
    current = {"ok": False, "checks": [{"name": "wall", "type": "t", "ok": False, "actual": 1.0}]}
    previous = {"ok": True, "checks": [{"name": "wall", "type": "t", "ok": True, "actual": 2.0}]}
    result = diff_validations(current, previous)
    assert len(result["checks_regressed"]) == 1
    assert result["checks_regressed"][0]["name"] == "wall"


def test_diff_detects_fix():
    current = {"ok": True, "checks": [{"name": "wall", "type": "t", "ok": True, "actual": 2.0}]}
    previous = {"ok": False, "checks": [{"name": "wall", "type": "t", "ok": False, "actual": 1.0}]}
    result = diff_validations(current, previous)
    assert len(result["checks_fixed"]) == 1
    assert result["checks_fixed"][0]["name"] == "wall"


def test_diff_detects_new_and_removed():
    current = {"ok": True, "checks": [{"name": "a", "type": "t", "ok": True}, {"name": "new", "type": "t2", "ok": True}]}
    previous = {"ok": True, "checks": [{"name": "a", "type": "t", "ok": True}, {"name": "old", "type": "t3", "ok": True}]}
    result = diff_validations(current, previous)
    assert len(result["checks_new"]) == 1
    assert result["checks_new"][0]["name"] == "new"
    assert len(result["checks_removed"]) == 1
    assert result["checks_removed"][0]["name"] == "old"


def test_diff_model_no_validation(tmp_path):
    init_workspace(tmp_path)
    new_model(tmp_path, "no_val")
    result = diff_model(tmp_path, "no_val")
    assert result["ok"] is False
    assert result["error"]["type"] == "NoValidation"


def test_validate_archives_before_overwrite(tmp_path):
    init_workspace(tmp_path)
    new_model(tmp_path, "arch_model")
    result = validate_model(tmp_path, "arch_model")
    assert result["ok"] is True

    # Second run should archive the first validation
    result2 = validate_model(tmp_path, "arch_model")
    assert result2["ok"] is True

    out = tmp_path / "models" / "arch_model" / "outputs"
    hist = out / "validation-history"
    assert hist.is_dir()
    archives = list(hist.glob("*.json"))
    assert len(archives) >= 1


def test_diff_compares_with_most_recent_archive(tmp_path):
    """Three validate runs: diff should compare current vs most recent archive."""
    init_workspace(tmp_path)
    new_model(tmp_path, "dm")
    root = tmp_path / "models" / "dm"
    root.joinpath("part.py").write_text("import build123d as b\nresult = b.Box(10,10,10)\n")
    root.joinpath("params.json").write_text("{}")
    root.joinpath("design.json").write_text(json.dumps({"intent": "dm", "features": [], "checks": []}))

    # Run validate 3 times → 2 archives
    validate_model(tmp_path, "dm")
    validate_model(tmp_path, "dm")
    validate_model(tmp_path, "dm")

    hist = tmp_path / "models" / "dm" / "outputs" / "validation-history"
    archives = sorted(hist.glob("*.json"), reverse=True)
    assert len(archives) >= 2

    result = diff_model(tmp_path, "dm")
    assert result["ok"] is True
    # Should compare against archives[0] (most recent previous run)
    assert archives[0].name in result["compared_with"]
