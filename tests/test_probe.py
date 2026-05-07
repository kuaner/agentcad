"""Tests for probe_model: cross-section geometry interrogation."""
from __future__ import annotations

import struct
from pathlib import Path

import pytest

from agentcad.probe import probe_model
from agentcad.workspace import init_workspace, new_model, outputs_dir


def _make_cube_stl(path: Path, size: float = 10.0) -> None:
    """Write a solid cube as binary STL with 12 triangles."""
    s = size
    faces = [
        # bottom (z=0)
        ((0,0,0), (s,0,0), (s,s,0)),
        ((0,0,0), (s,s,0), (0,s,0)),
        # top (z=s)
        ((0,0,s), (s,s,s), (s,0,s)),
        ((0,0,s), (0,s,s), (s,s,s)),
        # front (y=0)
        ((0,0,0), (s,0,s), (s,0,0)),
        ((0,0,0), (0,0,s), (s,0,s)),
        # back (y=s)
        ((0,s,0), (s,s,0), (s,s,s)),
        ((0,s,0), (s,s,s), (0,s,s)),
        # left (x=0)
        ((0,0,0), (0,s,0), (0,s,s)),
        ((0,0,0), (0,s,s), (0,0,s)),
        # right (x=s)
        ((s,0,0), (s,s,s), (s,s,0)),
        ((s,0,0), (s,0,s), (s,s,s)),
    ]
    buf = bytearray(80)  # header
    buf += struct.pack("<I", len(faces))
    for a, b, c in faces:
        buf += struct.pack("<3f", 0.0, 0.0, 0.0)  # normal (ignored)
        for v in (a, b, c):
            buf += struct.pack("<3f", *v)
        buf += struct.pack("<H", 0)
    path.write_bytes(bytes(buf))


@pytest.fixture()
def cube_project(tmp_path):
    init_workspace(tmp_path)
    new_model(tmp_path, "cube")
    out = outputs_dir(tmp_path, "cube")
    out.mkdir(parents=True, exist_ok=True)
    _make_cube_stl(out / "cube.stl", size=10.0)
    return tmp_path


def test_probe_missing_stl(tmp_path):
    init_workspace(tmp_path)
    new_model(tmp_path, "ghost")
    result = probe_model(tmp_path, "ghost", z_values=[5.0])
    assert result["ok"] is False
    assert result["error"]["type"] == "STLMissing"


def test_probe_single_z(cube_project):
    result = probe_model(cube_project, "cube", z_values=[5.0])
    assert result["ok"] is True
    assert result["z"] == 5.0
    section = result["section"]
    assert section["ok"] is True
    assert section["point_count"] > 0
    # Cube 10x10x10 centred at (5,5): outer radius from center should be ~7mm
    assert section["radius_outer_estimate"] > 5.0
    assert "suggested_checks" in result


def test_probe_multiple_z(cube_project):
    result = probe_model(cube_project, "cube", z_values=[2.0, 5.0, 8.0])
    assert result["ok"] is True
    assert "results" in result
    assert len(result["results"]) == 3
    for r in result["results"]:
        assert r["section"]["ok"] is True


def test_probe_no_intersection(cube_project):
    result = probe_model(cube_project, "cube", z_values=[50.0])
    assert result["ok"] is True
    # Single result – section should report no intersection
    section = result["section"]
    assert section["ok"] is False


def test_probe_with_region_solid(cube_project):
    # Region fully inside the cube XY at z=5
    result = probe_model(
        cube_project, "cube",
        z_values=[5.0],
        center=(5.0, 5.0),
        region=((3.0, 3.0), (7.0, 7.0)),
    )
    assert result["ok"] is True
    assert "region_section" in result
    # The cube has material surrounding the region, so points should exist
    assert result["region_section"].get("ok") is True
    assert "section_bbox_at_z" in result["suggested_checks"]


def test_probe_suggested_checks_format(cube_project):
    result = probe_model(cube_project, "cube", z_values=[5.0], center=(5.0, 5.0))
    assert result["ok"] is True
    sugg = result["suggested_checks"]
    assert "outer_diameter_at_z" in sugg
    outer = sugg["outer_diameter_at_z"]
    assert outer["type"] == "outer_diameter_at_z"
    assert outer["z"] == 5.0
    assert outer["center"] == [5.0, 5.0]
    assert isinstance(outer["expected"], float)
    assert outer["tolerance"] == 1.0
