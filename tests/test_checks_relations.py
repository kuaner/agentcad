from __future__ import annotations

from pathlib import Path

from agentcad.checks import CheckContext
from agentcad.checks.relations import evaluate_hole_accessibility


def test_hole_accessibility_uses_diameter_as_half_radius(monkeypatch, tmp_path: Path):
    captured = {}

    def fake_hole_accessibility(triangles, z, center, hole_radius, clearance_radius):
        captured["hole_radius"] = hole_radius
        captured["clearance_radius"] = clearance_radius
        return {"ok": True, "blocking_point_count": 0, "min_blocking_radius": None}

    monkeypatch.setattr("agentcad.checks.relations.hole_accessibility_at_z", fake_hole_accessibility)

    ctx = CheckContext(
        project=tmp_path,
        name="m",
        measure={},
        get_triangles=lambda: [],
        out_dir=tmp_path,
    )
    check = {
        "id": "h",
        "type": "hole_accessibility",
        "z": 2.0,
        "center": [0.0, 0.0],
        "hole_diameter": 4.5,
        "clearance_diameter": 12.0,
    }
    result = evaluate_hole_accessibility(check, ctx)
    assert result["ok"] is True
    assert captured["hole_radius"] == 2.25
    assert captured["clearance_radius"] == 6.0


def test_hole_accessibility_supports_y_axis(monkeypatch, tmp_path: Path):
    captured = {}

    def fake_hole_accessibility(triangles, axis, pos, center, hole_radius, clearance_radius):
        captured["axis"] = axis
        captured["pos"] = pos
        captured["center"] = center
        return {"ok": True, "blocking_point_count": 0, "min_blocking_radius": None}

    monkeypatch.setattr("agentcad.checks.relations.hole_accessibility_at_axis", fake_hole_accessibility)

    ctx = CheckContext(
        project=tmp_path,
        name="m",
        measure={},
        get_triangles=lambda: [],
        out_dir=tmp_path,
    )
    check = {
        "id": "side_hole_access",
        "type": "hole_accessibility",
        "axis": "y",
        "y": -10.0,
        "center": [-20.0, 38.0],
        "hole_diameter": 4.5,
        "clearance_diameter": 12.0,
    }
    result = evaluate_hole_accessibility(check, ctx)
    assert result["ok"] is True
    assert result["axis"] == "y"
    assert result["position"] == -10.0
    assert captured["axis"] == 1
    assert captured["pos"] == -10.0
    assert captured["center"] == (-20.0, 38.0)
