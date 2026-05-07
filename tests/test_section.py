"""Tests for section.py: cross-section segment extraction and SVG rendering."""
from __future__ import annotations

import struct
from pathlib import Path

import pytest

from agentcad.section import (
    AXIS_X, AXIS_Y, AXIS_Z,
    _empty_svg,
    render_section_svg,
    scan_profile,
    section_segments,
    write_section_svg,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _cube_triangles(size: float = 10.0):
    """Return triangle list for a solid cube [0,size]^3."""
    s = size
    faces = [
        ((0,0,0),(s,0,0),(s,s,0)), ((0,0,0),(s,s,0),(0,s,0)),
        ((0,0,s),(s,s,s),(s,0,s)), ((0,0,s),(0,s,s),(s,s,s)),
        ((0,0,0),(s,0,s),(s,0,0)), ((0,0,0),(0,0,s),(s,0,s)),
        ((0,s,0),(s,s,0),(s,s,s)), ((0,s,0),(s,s,s),(0,s,s)),
        ((0,0,0),(0,s,0),(0,s,s)), ((0,0,0),(0,s,s),(0,0,s)),
        ((s,0,0),(s,s,s),(s,s,0)), ((s,0,0),(s,0,s),(s,s,s)),
    ]
    return [((a[0],a[1],a[2]),(b[0],b[1],b[2]),(c[0],c[1],c[2])) for a,b,c in faces]


# ── section_segments ──────────────────────────────────────────────────────────

def test_section_segments_empty():
    assert section_segments([], AXIS_Z, 5.0) == []


def test_section_segments_z_midpoint():
    tris = _cube_triangles(10.0)
    segs = section_segments(tris, AXIS_Z, 5.0)
    assert len(segs) > 0
    for (u1, v1), (u2, v2) in segs:
        assert isinstance(u1, float) and isinstance(v1, float)


def test_section_segments_x_midpoint():
    tris = _cube_triangles(10.0)
    segs = section_segments(tris, AXIS_X, 5.0)
    assert len(segs) > 0


def test_section_segments_y_midpoint():
    tris = _cube_triangles(10.0)
    segs = section_segments(tris, AXIS_Y, 5.0)
    assert len(segs) > 0


def test_section_segments_outside_returns_empty():
    tris = _cube_triangles(10.0)
    segs = section_segments(tris, AXIS_Z, 50.0)
    assert segs == []


def test_section_segments_z_bbox_correct():
    tris = _cube_triangles(10.0)
    segs = section_segments(tris, AXIS_Z, 5.0)
    all_u = [p[0] for seg in segs for p in seg]
    all_v = [p[1] for seg in segs for p in seg]
    # Z section of a [0,10]^3 cube at z=5 should span X=0..10, Y=0..10
    assert min(all_u) == pytest.approx(0.0, abs=0.01)
    assert max(all_u) == pytest.approx(10.0, abs=0.01)
    assert min(all_v) == pytest.approx(0.0, abs=0.01)
    assert max(all_v) == pytest.approx(10.0, abs=0.01)


# ── scan_profile ──────────────────────────────────────────────────────────────

def test_scan_profile_empty():
    result = scan_profile([])
    assert result["ok"] is False


def test_scan_profile_z_basic():
    tris = _cube_triangles(10.0)
    result = scan_profile(tris, axis=AXIS_Z, samples=5)
    assert result["ok"] is True
    assert result["axis"] == "Z"
    assert len(result["profile"]) == 5
    for entry in result["profile"]:
        assert entry["u_size"] == pytest.approx(10.0, abs=0.1)
        assert entry["v_size"] == pytest.approx(10.0, abs=0.1)


def test_scan_profile_x():
    tris = _cube_triangles(10.0)
    result = scan_profile(tris, axis=AXIS_X, samples=5)
    assert result["ok"] is True
    assert result["axis"] == "X"


def test_scan_profile_step_detection():
    """A model with a sharp step should have step changes detected."""
    # Two cubes stacked: bottom 10x10x5, top 5x5x5 (narrower)
    tris = []
    # Bottom block [0,10]x[0,10]x[0,5]
    s = 10.0
    h = 5.0
    tris += [
        ((0,0,0),(s,0,0),(s,s,0)), ((0,0,0),(s,s,0),(0,s,0)),
        ((0,0,h),(s,s,h),(s,0,h)), ((0,0,h),(0,s,h),(s,s,h)),
        ((0,0,0),(s,0,h),(s,0,0)), ((0,0,0),(0,0,h),(s,0,h)),
        ((0,s,0),(s,s,0),(s,s,h)), ((0,s,0),(s,s,h),(0,s,h)),
        ((0,0,0),(0,s,0),(0,s,h)), ((0,0,0),(0,s,h),(0,0,h)),
        ((s,0,0),(s,s,h),(s,s,0)), ((s,0,0),(s,0,h),(s,s,h)),
    ]
    # Top block [2.5,7.5]x[2.5,7.5]x[5,10]
    a, b = 2.5, 7.5
    lo, hi = 5.0, 10.0
    tris += [
        ((a,a,lo),(b,a,lo),(b,b,lo)), ((a,a,lo),(b,b,lo),(a,b,lo)),
        ((a,a,hi),(b,b,hi),(b,a,hi)), ((a,a,hi),(a,b,hi),(b,b,hi)),
        ((a,a,lo),(b,a,hi),(b,a,lo)), ((a,a,lo),(a,a,hi),(b,a,hi)),
        ((a,b,lo),(b,b,lo),(b,b,hi)), ((a,b,lo),(b,b,hi),(a,b,hi)),
        ((a,a,lo),(a,b,lo),(a,b,hi)), ((a,a,lo),(a,b,hi),(a,a,hi)),
        ((b,a,lo),(b,b,hi),(b,b,lo)), ((b,a,lo),(b,a,hi),(b,b,hi)),
    ]
    result = scan_profile(tris, axis=AXIS_Z, samples=10, step_threshold=2.0)
    assert result["ok"] is True
    assert len(result["step_changes"]) >= 1
    step_pos = result["step_changes"][0]["pos"]
    assert 4.0 < step_pos < 6.0  # step should be near Z=5


# ── SVG rendering ─────────────────────────────────────────────────────────────

def test_render_section_svg_returns_string():
    tris = _cube_triangles(10.0)
    segs = section_segments(tris, AXIS_Z, 5.0)
    svg = render_section_svg(segs, AXIS_Z, 5.0)
    assert isinstance(svg, str)
    assert "<svg" in svg
    assert "Z = 5.00" in svg


def test_render_section_svg_empty():
    svg = render_section_svg([], AXIS_Z, 5.0)
    assert "<svg" in svg
    assert "no intersections" in svg


def test_render_section_svg_x_labels():
    tris = _cube_triangles(10.0)
    segs = section_segments(tris, AXIS_X, 5.0)
    svg = render_section_svg(segs, AXIS_X, 5.0)
    assert "YZ plane" in svg
    assert "Y (mm)" in svg


def test_write_section_svg(tmp_path):
    tris = _cube_triangles(10.0)
    out = tmp_path / "test_section.svg"
    result = write_section_svg(tris, AXIS_Z, 5.0, out)
    assert result["ok"] is True
    assert out.exists()
    content = out.read_text()
    assert "<svg" in content
    assert result["segment_count"] > 0
