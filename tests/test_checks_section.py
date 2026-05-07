from __future__ import annotations

from pathlib import Path

from agentcad.checks import CheckContext
from agentcad.checks.section import evaluate_diameter_decreases_along_z


def test_diameter_decreases_handles_failed_section_samples(monkeypatch, tmp_path: Path):
    def fake_section_radius_at_z(triangles, z, center):
        return {"ok": False, "error": "no intersection", "diameter_outer_estimate": None}

    monkeypatch.setattr("agentcad.checks.section.section_radius_at_z", fake_section_radius_at_z)
    ctx = CheckContext(project=tmp_path, name="m", measure={}, get_triangles=lambda: [], out_dir=tmp_path)
    result = evaluate_diameter_decreases_along_z(
        {"id": "taper", "type": "diameter_decreases_along_z", "z_values": [0.0, 1.0, 2.0]},
        ctx,
    )
    assert result["ok"] is False
    assert result["error"]["type"] == "SectionSamplingError"
