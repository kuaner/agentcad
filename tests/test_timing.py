"""Tests for P4.1 timing instrumentation: validation payload timings."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentcad.validate import _validation_payload, timed_stage
from agentcad.workspace import init_workspace, new_model, model_dir


@pytest.fixture()
def project(tmp_path):
    init_workspace(tmp_path)
    new_model(tmp_path, "thing")
    return tmp_path


class TestTimedStage:
    def test_records_duration(self):
        timings = {}
        with timed_stage(timings, "build"):
            pass  # instant
        assert "buildMs" in timings
        assert timings["buildMs"] >= 0

    def test_records_nonzero_duration(self):
        timings = {}
        with timed_stage(timings, "slow"):
            # Sleep is not needed — perf_counter resolution is sufficient.
            for _ in range(10000):
                pass
        assert timings["slowMs"] > 0

    def test_multiple_stages(self):
        timings = {}
        with timed_stage(timings, "build"):
            pass
        with timed_stage(timings, "measure"):
            pass
        assert "buildMs" in timings
        assert "measureMs" in timings


class TestValidationPayloadTimings:
    def test_payload_without_timings(self):
        payload = _validation_payload("test", [], artifacts={})
        assert "timings" not in payload

    def test_payload_with_timings(self):
        timings = {"buildMs": 1200.4, "measureMs": 34.2, "totalMs": 1234.6}
        payload = _validation_payload("test", [], artifacts={}, timings=timings)
        assert payload["timings"] == timings
        assert payload["timings"]["buildMs"] > 0

    def test_payload_with_zero_timings(self):
        timings = {"buildMs": 0}
        payload = _validation_payload("test", [], artifacts={}, timings=timings)
        assert payload["timings"]["buildMs"] == 0

    def test_timing_fields_are_numeric(self):
        timings = {"buildMs": 1.5, "measureMs": 0.3}
        payload = _validation_payload("test", [], artifacts={}, timings=timings)
        for key, value in payload["timings"].items():
            assert isinstance(value, (int, float))


class TestBatchSummaryTimings:
    def test_summary_includes_durationMs_from_timings(self):
        payload = {
            "ok": True,
            "stage": "validate",
            "checks": [],
            "timings": {"buildMs": 100, "totalMs": 150},
            "artifacts": {},
        }
        from agentcad.batch import _target_summary, ValidationTarget
        target = ValidationTarget(kind="model", name="demo", path=Path("/tmp"), variant=None)
        summary = _target_summary(target, payload)
        assert summary["durationMs"] == 150
        assert summary["timings"] == {"buildMs": 100, "totalMs": 150}

    def test_summary_without_timings_has_null_durationMs(self):
        payload = {
            "ok": True,
            "stage": "validate",
            "checks": [],
            "artifacts": {},
        }
        from agentcad.batch import _target_summary, ValidationTarget
        target = ValidationTarget(kind="model", name="demo", path=Path("/tmp"), variant=None)
        summary = _target_summary(target, payload)
        assert summary["durationMs"] is None
        assert summary["timings"] is None