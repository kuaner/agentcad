from __future__ import annotations

from pathlib import Path

from agentcad.checks import CheckContext
from agentcad.checks.relations import (
    evaluate_hole_accessibility,
    evaluate_min_wall_thickness,
    _sample_positions,
)


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


class TestSamplePositions:
    def test_two_samples(self):
        positions = _sample_positions(0.0, 10.0, 2)
        assert positions == [0.0, 10.0]

    def test_six_samples(self):
        positions = _sample_positions(0.0, 10.0, 6)
        assert len(positions) == 6
        assert positions[0] == 0.0
        assert positions[-1] == 10.0

    def test_one_sample(self):
        positions = _sample_positions(0.0, 10.0, 1)
        assert positions == [0.0]


class TestMinWallThicknessRangeMode:
    def test_range_mode_passes_all_slices(self, monkeypatch, tmp_path: Path):
        """When all slices exceed minimum, range mode passes."""

        def fake_thickness(triangles, z, region=None, sample_resolution=0.5):
            return {"ok": True, "min_thickness_mm": 2.5, "min_pair": None, "point_count": 100}

        monkeypatch.setattr("agentcad.checks.relations.min_wall_thickness_at_z", fake_thickness)

        ctx = CheckContext(
            project=tmp_path,
            name="m",
            measure={},
            get_triangles=lambda: [],
            out_dir=tmp_path,
        )
        check = {
            "id": "wall_range",
            "type": "min_wall_thickness",
            "axis": "z",
            "range": [0, 10],
            "samples": 6,
            "region": [[0, 0], [10, 10]],
            "min_mm": 1.0,
        }
        result = evaluate_min_wall_thickness(check, ctx)
        assert result["ok"] is True
        assert result["actual_mm"] == 2.5
        assert result["axis"] == "z"
        assert result["range"] == [0, 10]
        assert len(result["slice_results"]) == 6

    def test_range_mode_fails_one_slice(self, monkeypatch, tmp_path: Path):
        """When one slice is too thin, range mode fails and reports worst."""
        thickness_by_z = {2.0: 0.5, 4.0: 2.5, 6.0: 2.5, 8.0: 2.5, 10.0: 2.5, 0.0: 2.5}

        def fake_thickness(triangles, z, region=None, sample_resolution=0.5):
            mm = thickness_by_z.get(z, 2.5)
            return {"ok": True, "min_thickness_mm": mm, "min_pair": None, "point_count": 100}

        monkeypatch.setattr("agentcad.checks.relations.min_wall_thickness_at_z", fake_thickness)

        ctx = CheckContext(
            project=tmp_path,
            name="m",
            measure={},
            get_triangles=lambda: [],
            out_dir=tmp_path,
        )
        check = {
            "id": "wall_range",
            "type": "min_wall_thickness",
            "axis": "z",
            "range": [0, 10],
            "samples": 6,
            "region": [[0, 0], [10, 10]],
            "min_mm": 1.0,
        }
        result = evaluate_min_wall_thickness(check, ctx)
        assert result["ok"] is False
        assert result["actual_mm"] == 0.5
        assert result["worst_position"] == 2.0

    def test_range_mode_no_valid_slices(self, monkeypatch, tmp_path: Path):
        """When no slices produce valid results, range mode fails."""
        def fake_thickness(triangles, z, region=None, sample_resolution=0.5):
            return {"ok": False, "error": "no mesh at this z"}

        monkeypatch.setattr("agentcad.checks.relations.min_wall_thickness_at_z", fake_thickness)

        ctx = CheckContext(
            project=tmp_path,
            name="m",
            measure={},
            get_triangles=lambda: [],
            out_dir=tmp_path,
        )
        check = {
            "id": "wall_range",
            "type": "min_wall_thickness",
            "axis": "z",
            "range": [0, 10],
            "samples": 3,
            "region": [[0, 0], [10, 10]],
            "min_mm": 1.0,
        }
        result = evaluate_min_wall_thickness(check, ctx)
        assert result["ok"] is False
        assert result["error"]["type"] == "ThicknessError"

    def test_single_plane_still_works(self, monkeypatch, tmp_path: Path):
        """Single-plane mode backward compatibility."""
        def fake_thickness(triangles, z, region=None, sample_resolution=0.5):
            return {"ok": True, "min_thickness_mm": 2.0, "min_pair": None, "point_count": 100}

        monkeypatch.setattr("agentcad.checks.relations.min_wall_thickness_at_z", fake_thickness)

        ctx = CheckContext(
            project=tmp_path,
            name="m",
            measure={},
            get_triangles=lambda: [],
            out_dir=tmp_path,
        )
        check = {
            "id": "wall_single",
            "type": "min_wall_thickness",
            "z": 3.0,
            "region": [[0, 0], [10, 10]],
            "min_mm": 1.0,
        }
        result = evaluate_min_wall_thickness(check, ctx)
        assert result["ok"] is True
        assert result["z"] == 3.0
        assert "axis" not in result  # single plane should not have axis/range fields

    def test_unsupported_axis_returns_error(self, tmp_path: Path):
        ctx = CheckContext(
            project=tmp_path,
            name="m",
            measure={},
            get_triangles=lambda: [],
            out_dir=tmp_path,
        )
        check = {
            "id": "wall_range",
            "type": "min_wall_thickness",
            "axis": "x",
            "range": [0, 10],
            "samples": 3,
            "region": [[0, 0], [10, 10]],
            "min_mm": 1.0,
        }
        result = evaluate_min_wall_thickness(check, ctx)
        assert result["ok"] is False
        assert result["error"]["type"] == "CheckInputError"
