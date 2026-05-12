"""Tests for P4.3 clean command: artifact retention and cleanup."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentcad.clean import clean_model, _clean_all, _is_protected
from agentcad.workspace import init_workspace, new_model, model_dir, outputs_dir


@pytest.fixture()
def project(tmp_path):
    init_workspace(tmp_path)
    new_model(tmp_path, "thing")
    return tmp_path


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class TestCleanDryRun:
    def test_dry_run_does_not_delete(self, project):
        out_dir = outputs_dir(project, "thing")
        history_dir = out_dir / "validation-history"
        history_dir.mkdir(parents=True, exist_ok=True)
        # Write 5 history files.
        for i in range(5):
            _write_json(history_dir / f"run_{i}.json", {"ok": True})
        result = clean_model(project, "thing", dry_run=True)
        assert result["dry_run"] is True
        assert result["bytes_freed"] == 0
        # Files should still exist.
        assert len(list(history_dir.glob("*.json"))) == 5

    def test_dry_run_reports_old_history(self, project):
        out_dir = outputs_dir(project, "thing")
        history_dir = out_dir / "validation-history"
        history_dir.mkdir(parents=True, exist_ok=True)
        for i in range(15):
            _write_json(history_dir / f"run_{i}.json", {"ok": True})
        result = clean_model(project, "thing", dry_run=True, history_max=10)
        # Should report that files would be removed (but not actually remove).
        assert result["dry_run"] is True
        # All files still present.
        assert len(list(history_dir.glob("*.json"))) == 15


class TestCleanValidationHistory:
    def test_removes_old_history_files(self, project):
        out_dir = outputs_dir(project, "thing")
        history_dir = out_dir / "validation-history"
        history_dir.mkdir(parents=True, exist_ok=True)
        # Write 15 history files.
        for i in range(15):
            _write_json(history_dir / f"run_{i}.json", {"ok": True})
        result = clean_model(project, "thing", dry_run=False, history_max=10)
        assert result["bytes_freed"] > 0
        # Should keep only 10 most recent.
        remaining = list(history_dir.glob("*.json"))
        assert len(remaining) <= 10

    def test_keeps_all_if_under_limit(self, project):
        out_dir = outputs_dir(project, "thing")
        history_dir = out_dir / "validation-history"
        history_dir.mkdir(parents=True, exist_ok=True)
        for i in range(5):
            _write_json(history_dir / f"run_{i}.json", {"ok": True})
        result = clean_model(project, "thing", dry_run=False, history_max=10)
        # 5 files, limit is 10 → no deletions.
        assert len(result["removed"]) == 0


class TestCleanDebugArtifacts:
    def test_removes_debug_svgs(self, project):
        out_dir = outputs_dir(project, "thing")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "debug.hole_dia.z5.00.svg").write_text("<svg></svg>")
        (out_dir / "debug.wall.z2.00.json").write_text(json.dumps({"ok": True}))
        result = clean_model(project, "thing", dry_run=False, debug=True)
        assert result["bytes_freed"] > 0
        assert not (out_dir / "debug.hole_dia.z5.00.svg").exists()

    def test_skips_debug_if_flag_false(self, project):
        out_dir = outputs_dir(project, "thing")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "debug.hole_dia.z5.00.svg").write_text("<svg></svg>")
        result = clean_model(project, "thing", dry_run=False, debug=False)
        assert (out_dir / "debug.hole_dia.z5.00.svg").exists()


class TestCleanProtectedArtifacts:
    def test_does_not_delete_validation_json(self, project):
        out_dir = outputs_dir(project, "thing")
        out_dir.mkdir(parents=True, exist_ok=True)
        _write_json(out_dir / "validation.json", {"ok": True})
        result = clean_model(project, "thing", dry_run=False)
        assert (out_dir / "validation.json").exists()

    def test_does_not_delete_stl(self, project):
        out_dir = outputs_dir(project, "thing")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "thing.stl").write_text("fake stl")
        result = clean_model(project, "thing", dry_run=False)
        assert (out_dir / "thing.stl").exists()

    def test_does_not_delete_step(self, project):
        out_dir = outputs_dir(project, "thing")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "thing.step").write_text("fake step")
        result = clean_model(project, "thing", dry_run=False)
        assert (out_dir / "thing.step").exists()

    def test_does_not_delete_build_json(self, project):
        out_dir = outputs_dir(project, "thing")
        out_dir.mkdir(parents=True, exist_ok=True)
        _write_json(out_dir / "build.json", {"ok": True})
        result = clean_model(project, "thing", dry_run=False)
        assert (out_dir / "build.json").exists()


class TestCleanPreviewSVGs:
    def test_does_not_clean_previews_by_default(self, project):
        out_dir = outputs_dir(project, "thing")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "preview.iso.svg").write_text("<svg></svg>")
        result = clean_model(project, "thing", dry_run=False, previews=False)
        assert (out_dir / "preview.iso.svg").exists()

    def test_cleans_previews_with_flag(self, project):
        out_dir = outputs_dir(project, "thing")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "preview.iso.svg").write_text("<svg></svg>")
        result = clean_model(project, "thing", dry_run=False, previews=True)
        assert not (out_dir / "preview.iso.svg").exists()

    def test_preview_html_is_protected_even_with_flag(self, project):
        out_dir = outputs_dir(project, "thing")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "preview.html").write_text("<html></html>")
        result = clean_model(project, "thing", dry_run=False, previews=True)
        assert (out_dir / "preview.html").exists()


class TestCleanAll:
    def test_clean_all_cleans_multiple_models(self, project):
        new_model(project, "thing2")
        out1 = outputs_dir(project, "thing")
        out2 = outputs_dir(project, "thing2")
        out1.mkdir(parents=True, exist_ok=True)
        out2.mkdir(parents=True, exist_ok=True)
        (out1 / "debug.test.svg").write_text("<svg></svg>")
        (out2 / "debug.test.svg").write_text("<svg></svg>")
        result = _clean_all(project, dry_run=False)
        assert result["model"] is None
        assert len(result["models"]) == 2
        assert result["bytes_freed"] > 0


class TestIsProtected:
    def test_validation_json_is_protected(self):
        assert _is_protected(Path("validation.json"), Path("/tmp/out"))

    def test_build_json_is_protected(self):
        assert _is_protected(Path("build.json"), Path("/tmp/out"))

    def test_stl_is_protected(self):
        assert _is_protected(Path("thing.stl"), Path("/tmp/thing/outputs"))

    def test_debug_svg_is_not_protected(self):
        assert not _is_protected(Path("debug.hole.svg"), Path("/tmp/out"))