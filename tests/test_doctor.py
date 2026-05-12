"""Tests for P3.1 doctor command: workflow state diagnostics."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentcad.doctor import run_model_doctor, DoctorFinding, _determine_state, _finding_to_dict
from agentcad.workspace import init_workspace, new_model, model_dir, outputs_dir


def _write_design(mdir: Path, design: dict) -> None:
    (mdir / "design.json").write_text(json.dumps(design), encoding="utf-8")


@pytest.fixture()
def project(tmp_path):
    init_workspace(tmp_path)
    new_model(tmp_path, "thing")
    return tmp_path


# ── workflow state determination ──────────────────────────────────────────


class TestDetermineState:
    def test_missing_design(self):
        state = _determine_state([], {"design_json": False})
        assert state == "missing_design"

    def test_needs_precheck(self):
        state = _determine_state([], {"design_json": True, "precheck_json": False})
        assert state == "needs_precheck"

    def test_needs_build(self):
        state = _determine_state([], {
            "design_json": True, "precheck_json": True,
            "build_json": False, "stl": False,
        })
        assert state == "needs_build"

    def test_needs_validation(self):
        state = _determine_state([], {
            "design_json": True, "precheck_json": True,
            "build_json": True, "stl": True,
            "validation_json": False,
        })
        assert state == "needs_validation"

    def test_needs_review(self):
        state = _determine_state([], {
            "design_json": True, "precheck_json": True,
            "build_json": True, "stl": True,
            "validation_json": True, "validation_ok": True,
            "review_json": False,
        })
        assert state == "needs_review"

    def test_ready_for_delivery(self):
        state = _determine_state([], {
            "design_json": True, "precheck_json": True,
            "build_json": True, "stl": True,
            "validation_json": True, "validation_ok": True,
            "review_json": True, "review_ok": True,
        })
        assert state == "ready_for_delivery"

    def test_blocked_with_blocking_finding(self):
        findings = [DoctorFinding("design_missing", "blocking", "no design")]
        state = _determine_state(findings, {"design_json": True})
        assert state == "blocked"


# ── diagnostic rules ────────────────────────────────────────────────────────

DESIGN = {
    "features": [{"id": "shell", "checks": ["bbox"]}],
    "checks": [{"id": "bbox", "type": "bbox_size", "expected": [10, 10, 10], "tolerance": 0.1}],
}


class TestDoctorRules:
    def test_fresh_scaffold_needs_precheck(self, project):
        result = run_model_doctor(project, "thing")
        assert result["state"] in ("needs_precheck", "blocked")
        assert any(f["id"] == "precheck_missing" for f in result["findings"])

    def test_with_design_recommends_precheck(self, project):
        mdir = model_dir(project, "thing")
        _write_design(mdir, DESIGN)
        result = run_model_doctor(project, "thing")
        assert any(f["id"] == "precheck_missing" for f in result["findings"])

    def test_built_but_unvalidated(self, project):
        mdir = model_dir(project, "thing")
        out_dir = outputs_dir(project, "thing")
        out_dir.mkdir(parents=True, exist_ok=True)
        _write_design(mdir, DESIGN)
        (out_dir / "build.json").write_text(json.dumps({"ok": True}))
        (out_dir / "thing.stl").write_text("fake stl")
        result = run_model_doctor(project, "thing")
        assert any(f["id"] == "validation_missing" for f in result["findings"])

    def test_validated_but_unreviewed(self, project):
        mdir = model_dir(project, "thing")
        out_dir = outputs_dir(project, "thing")
        out_dir.mkdir(parents=True, exist_ok=True)
        _write_design(mdir, DESIGN)
        (out_dir / "build.json").write_text(json.dumps({"ok": True}))
        (out_dir / "thing.stl").write_text("fake stl")
        (out_dir / "validation.json").write_text(json.dumps({"ok": True}))
        result = run_model_doctor(project, "thing")
        assert any(f["id"] == "review_missing" for f in result["findings"])

    def test_source_newer_than_build(self, project):
        mdir = model_dir(project, "thing")
        out_dir = outputs_dir(project, "thing")
        out_dir.mkdir(parents=True, exist_ok=True)
        _write_design(mdir, DESIGN)
        # Write build.json first, then part.py (so part.py is newer).
        (out_dir / "build.json").write_text(json.dumps({"ok": True}))
        (mdir / "part.py").write_text("result = None", encoding="utf-8")
        result = run_model_doctor(project, "thing")
        assert any(f["id"] == "source_newer_than_build" for f in result["findings"])

    def test_validated_model_with_preview_missing(self, project):
        mdir = model_dir(project, "thing")
        out_dir = outputs_dir(project, "thing")
        out_dir.mkdir(parents=True, exist_ok=True)
        _write_design(mdir, DESIGN)
        (out_dir / "build.json").write_text(json.dumps({"ok": True}))
        (out_dir / "thing.stl").write_text("fake stl")
        (out_dir / "validation.json").write_text(json.dumps({"ok": True}))
        result = run_model_doctor(project, "thing")
        assert any(f["id"] == "preview_missing" for f in result["findings"])

    def test_missing_design_is_blocking(self, project):
        mdir = model_dir(project, "thing")
        design_path = mdir / "design.json"
        if design_path.exists():
            design_path.unlink()
        result = run_model_doctor(project, "thing")
        assert any(
            f["id"] == "design_missing" and f["severity"] == "blocking"
            for f in result["findings"]
        )

    def test_fully_reviewed_ready(self, project):
        mdir = model_dir(project, "thing")
        out_dir = outputs_dir(project, "thing")
        out_dir.mkdir(parents=True, exist_ok=True)
        _write_design(mdir, DESIGN)
        (mdir / "part.py").write_text("result = None")
        (out_dir / "build.json").write_text(json.dumps({"ok": True}))
        (out_dir / "thing.stl").write_text("fake stl")
        (out_dir / "thing.step").write_text("fake step")
        (out_dir / "precheck.json").write_text(json.dumps({"ok": True}))
        (out_dir / "validation.json").write_text(json.dumps({"ok": True}))
        (out_dir / "review.json").write_text(json.dumps({"ok": True}))
        (out_dir / "preview.html").write_text("<html></html>")
        (out_dir / "preview.iso.svg").write_text("<svg></svg>")
        result = run_model_doctor(project, "thing")
        assert result["state"] == "ready_for_delivery"
        blocking = [f for f in result["findings"] if f["severity"] == "blocking"]
        assert blocking == []

    def test_next_command_is_first_blocking(self, project):
        mdir = model_dir(project, "thing")
        design_path = mdir / "design.json"
        if design_path.exists():
            design_path.unlink()
        result = run_model_doctor(project, "thing")
        assert result["next_command"] is not None


# ── DoctorFinding serialization ──────────────────────────────────────────


class TestFindingToDict:
    def test_basic_finding(self):
        f = DoctorFinding("test_id", "warning", "test message")
        d = _finding_to_dict(f)
        assert d["id"] == "test_id"
        assert d["severity"] == "warning"
        assert d["message"] == "test message"
        assert "next_command" not in d

    def test_finding_with_command(self):
        f = DoctorFinding("build_missing", "blocking", "no build", next_command="agentcad build thing")
        d = _finding_to_dict(f)
        assert d["next_command"] == "agentcad build thing"