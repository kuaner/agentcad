"""Failure-mode cookbook fixtures for agent modeling accuracy."""
from __future__ import annotations

import json
from pathlib import Path

from agentcad.contract import evaluate_feature_evidence_matrix_dict


ROOT = Path(__file__).resolve().parents[1] / "examples" / "cadbench"


def test_cadbench_cases_define_expected_evidence():
    cases = [
        "shallow-hole",
        "edge-breakout",
        "thin-wall",
        "suspended-rib",
        "assembly-eccentricity",
    ]

    for case in cases:
        expected = json.loads((ROOT / case / "expected.json").read_text(encoding="utf-8"))
        assert (ROOT / case / "prompt.md").exists()
        assert expected["required_evidence"]
        assert expected["checks"]


def test_failure_mode_matrix_matches_cadbench_expectations():
    for expected_path in sorted(ROOT.glob("*/expected.json")):
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        design = {
            "features": [{"id": "feature", "checks": []}],
            "checks": [],
            "failure_modes": [
                {
                    "id": expected_path.parent.name,
                    "mode": expected["failure_mode"],
                    "severity": "high",
                    "affects": ["feature"],
                    "required_evidence": expected["required_evidence"],
                }
            ],
        }

        row = evaluate_feature_evidence_matrix_dict(design)[0]

        for column in expected["required_evidence"]:
            assert column in row["required_evidence"]
