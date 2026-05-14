"""CADBench contract fixtures for measurable modeling-quality gates."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentcad.cadbench import evaluate_cadbench, evaluate_cadbench_case


ROOT = Path(__file__).resolve().parents[1] / "examples" / "cadbench"
CASES = [
    "shallow-hole",
    "edge-breakout",
    "thin-wall",
    "suspended-rib",
    "assembly-eccentricity",
]
EXPECTED_FIELDS = {
    "feature",
    "failure_mode",
    "required_evidence",
    "checks",
    "suggested_checks",
    "probe_command_contains",
    "max_placeholder_count",
}


@pytest.mark.parametrize("case", CASES)
def test_cadbench_case_files_are_complete(case):
    case_dir = ROOT / case
    assert (case_dir / "prompt.md").exists()
    assert (case_dir / "design.json").exists()
    assert (case_dir / "expected.json").exists()


@pytest.mark.parametrize("case", CASES)
def test_cadbench_expected_schema(case):
    expected = json.loads((ROOT / case / "expected.json").read_text(encoding="utf-8"))
    assert EXPECTED_FIELDS <= set(expected)
    assert isinstance(expected["required_evidence"], list)
    assert isinstance(expected["checks"], list)
    assert isinstance(expected["suggested_checks"], list)
    assert isinstance(expected["max_placeholder_count"], int)


@pytest.mark.parametrize("case", CASES)
def test_cadbench_required_evidence_coverage(case):
    result = evaluate_cadbench_case(ROOT / case)
    check = _case_check(result, "required_evidence_covered")
    assert check["ok"], check["evidence"]


@pytest.mark.parametrize("case", CASES)
def test_cadbench_candidate_check_types_cover_expected_checks(case):
    result = evaluate_cadbench_case(ROOT / case)
    check = _case_check(result, "candidate_check_types_covered")
    assert check["ok"], check["evidence"]


@pytest.mark.parametrize("case", CASES)
def test_cadbench_suggestions_cover_required_suggested_checks(case):
    result = evaluate_cadbench_case(ROOT / case)
    check = _case_check(result, "suggested_check_types_covered")
    assert check["ok"], check["evidence"]


@pytest.mark.parametrize("case", CASES)
def test_cadbench_placeholder_budget(case):
    result = evaluate_cadbench_case(ROOT / case)
    check = _case_check(result, "placeholder_budget")
    assert check["ok"], check["evidence"]


@pytest.mark.parametrize("case", CASES)
def test_cadbench_probe_plan_matches_failure_mode(case):
    result = evaluate_cadbench_case(ROOT / case)
    check = _case_check(result, "probe_expectations_covered")
    assert check["ok"], check["evidence"]


def test_cadbench_aggregate_passes_all_cases():
    result = evaluate_cadbench(ROOT)
    assert result["ok"] is True
    assert result["case_count"] == 5
    assert result["passed"] == 5
    assert result["failed"] == 0
    assert result["metrics"]["placeholder_count"] == 0


def _case_check(result: dict, name: str) -> dict:
    return next(check for check in result["checks"] if check["name"] == name)
