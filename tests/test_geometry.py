"""Tests for geometry.py: pure shape clearance and accessibility primitives."""
from __future__ import annotations

import pytest

from agentcad.geometry import (
    aabb_axis_overlap,
    hole_accessibility_at_axis,
    hole_accessibility_at_z,
    min_clearance_3d,
    min_wall_thickness_at_z,
    parse_shape,
    shape_aabb,
    xy_clearance,
)


def _solid_cube(size=10.0, ox=0.0, oy=0.0, oz=0.0):
    s = size
    pts = [(ox + dx, oy + dy, oz + dz)
           for dx in (0, s) for dy in (0, s) for dz in (0, s)]
    faces_idx = [
        (0, 4, 6, 2), (1, 3, 7, 5),
        (0, 1, 5, 4), (2, 6, 7, 3),
        (0, 2, 3, 1), (4, 5, 7, 6),
    ]
    triangles = []
    for a, b, c, d in faces_idx:
        triangles.append((pts[a], pts[b], pts[c]))
        triangles.append((pts[a], pts[c], pts[d]))
    return triangles


# ── shape_aabb ────────────────────────────────────────────────────────────────

def test_shape_aabb_box():
    aabb = shape_aabb({"type": "box",
                       "x_range": [-5, 5], "y_range": [0, 10], "z_range": [0, 4]})
    assert aabb == {"min": [-5, 0, 0], "max": [5, 10, 4]}


def test_shape_aabb_cylinder_z():
    aabb = shape_aabb({"type": "cylinder", "axis": "z",
                       "center": [10, 5], "radius": 2.5, "z_range": [0, 8]})
    assert aabb == {"min": [7.5, 2.5, 0], "max": [12.5, 7.5, 8]}


def test_shape_aabb_cylinder_y():
    aabb = shape_aabb({"type": "cylinder", "axis": "y",
                       "center": [0, 20], "radius": 2.25, "y_range": [16, 20]})
    assert aabb == {"min": [-2.25, 16, 17.75], "max": [2.25, 20, 22.25]}


def test_shape_aabb_unsupported():
    with pytest.raises(ValueError):
        shape_aabb({"type": "torus"})


# ── aabb_axis_overlap ─────────────────────────────────────────────────────────

def test_aabb_axis_overlap_positive():
    a = {"min": [0, 0, 0], "max": [10, 10, 10]}
    b = {"min": [5, 0, 0], "max": [15, 10, 10]}
    assert aabb_axis_overlap(a, b, 0) == 5  # overlap [5,10]


def test_aabb_axis_overlap_separated():
    a = {"min": [0, 0, 0], "max": [10, 10, 10]}
    b = {"min": [12, 0, 0], "max": [20, 10, 10]}
    assert aabb_axis_overlap(a, b, 0) == -2  # gap of 2


# ── xy_clearance ──────────────────────────────────────────────────────────────

def test_xy_clearance_circle_circle_separated():
    a = {"type": "cylinder", "axis": "z", "center": [0, 0], "radius": 1.0, "z_range": [0, 10]}
    b = {"type": "cylinder", "axis": "z", "center": [5, 0], "radius": 1.0, "z_range": [0, 10]}
    result = xy_clearance(a, b)
    assert result["clearance_mm"] == pytest.approx(3.0)


def test_xy_clearance_circle_circle_touching():
    a = {"type": "cylinder", "axis": "z", "center": [0, 0], "radius": 2.0, "z_range": [0, 10]}
    b = {"type": "cylinder", "axis": "z", "center": [4, 0], "radius": 2.0, "z_range": [0, 10]}
    result = xy_clearance(a, b)
    assert result["clearance_mm"] == pytest.approx(0.0)


def test_xy_clearance_circle_rect_intrudes():
    """Reproduces the mounting_bracket bug."""
    hole = {"type": "cylinder", "axis": "z",
            "center": [-15, 15], "radius": 2.25, "z_range": [0, 4]}
    wall = {"type": "box",
            "x_range": [-25, 25], "y_range": [16, 20], "z_range": [0, 30]}
    result = xy_clearance(hole, wall)
    assert result["clearance_mm"] == pytest.approx(-1.25)


def test_xy_clearance_rect_rect():
    a = {"type": "box", "x_range": [0, 10], "y_range": [0, 10], "z_range": [0, 1]}
    b = {"type": "box", "x_range": [12, 20], "y_range": [0, 10], "z_range": [0, 1]}
    result = xy_clearance(a, b)
    assert result["clearance_mm"] == pytest.approx(2.0)


# ── min_clearance_3d ──────────────────────────────────────────────────────────

def test_min_clearance_3d_z_separated_no_interference():
    """Even though XY interferes, Z separation keeps them apart."""
    a = {"type": "box", "x_range": [-5, 5], "y_range": [-5, 5], "z_range": [0, 4]}
    b = {"type": "box", "x_range": [0, 10], "y_range": [0, 10], "z_range": [10, 20]}
    result = min_clearance_3d(a, b)
    assert result["interferes"] is False
    assert result["z_overlap_mm"] == -6  # 6mm gap
    assert result["clearance_mm"] == pytest.approx(6.0)


def test_min_clearance_3d_full_interference():
    a = {"type": "cylinder", "axis": "z",
         "center": [-15, 15], "radius": 2.25, "z_range": [0, 4]}
    b = {"type": "box",
         "x_range": [-25, 25], "y_range": [16, 20], "z_range": [0, 30]}
    result = min_clearance_3d(a, b)
    assert result["interferes"] is True
    assert result["clearance_mm"] == pytest.approx(-1.25)
    assert result["z_overlap_mm"] == 4


def test_min_clearance_3d_safe_position():
    """Hole moved 2mm away clears the wall."""
    a = {"type": "cylinder", "axis": "z",
         "center": [-15, 13], "radius": 2.25, "z_range": [0, 4]}
    b = {"type": "box",
         "x_range": [-25, 25], "y_range": [16, 20], "z_range": [0, 30]}
    result = min_clearance_3d(a, b)
    assert result["interferes"] is False
    assert result["clearance_mm"] == pytest.approx(0.75)


# ── parse_shape ───────────────────────────────────────────────────────────────

def test_parse_shape_valid_box():
    shape = parse_shape({"type": "box",
                         "x_range": [0, 1], "y_range": [0, 1], "z_range": [0, 1]})
    assert shape["type"] == "box"


def test_parse_shape_invalid_type():
    with pytest.raises(ValueError, match="unsupported shape type"):
        parse_shape({"type": "ellipsoid"})


def test_parse_shape_missing_field():
    with pytest.raises(ValueError, match="missing required field"):
        parse_shape({"type": "box", "x_range": [0, 1], "y_range": [0, 1]})


def test_parse_shape_cylinder_axis_validation():
    with pytest.raises(ValueError, match="cylinder axis must be"):
        parse_shape({"type": "cylinder", "axis": "w",
                     "center": [0, 0], "radius": 1, "z_range": [0, 1]})


# ── hole_accessibility_at_z ───────────────────────────────────────────────────

def test_hole_accessibility_clear():
    """Cube at origin, sample a Z section far from material."""
    cube = _solid_cube(size=10.0)
    result = hole_accessibility_at_z(cube, z=5.0,
                                     center=(50, 50), hole_radius=2,
                                     clearance_radius=5)
    assert result["ok"] is True
    assert result["blocking_point_count"] == 0


def test_hole_accessibility_blocked_by_wall():
    """Place the cube next to a hypothetical hole; tool envelope hits material."""
    cube = _solid_cube(size=10.0, ox=3.0, oy=-5.0)
    result = hole_accessibility_at_z(cube, z=5.0,
                                     center=(0, 0), hole_radius=1.0,
                                     clearance_radius=6.0)
    assert result["ok"] is False
    assert result["blocking_point_count"] > 0


def test_hole_accessibility_y_axis_clear_corridor():
    """Y-axis access checks use an XZ plane and center=(x,z)."""
    cube = _solid_cube(size=10.0, ox=20.0, oy=0.0, oz=20.0)
    result = hole_accessibility_at_axis(
        cube,
        axis=1,
        pos=5.0,
        center=(0.0, 0.0),
        hole_radius=1.0,
        clearance_radius=6.0,
    )
    assert result["ok"] is True


def test_hole_accessibility_y_axis_blocked_corridor():
    """Material in the XZ annulus around a Y-axis hole blocks access."""
    cube = _solid_cube(size=2.0, ox=3.0, oy=0.0, oz=-1.0)
    result = hole_accessibility_at_axis(
        cube,
        axis=1,
        pos=1.0,
        center=(0.0, 0.0),
        hole_radius=1.0,
        clearance_radius=6.0,
    )
    assert result["ok"] is False
    assert result["blocking_point_count"] > 0


# ── min_wall_thickness_at_z ───────────────────────────────────────────────────

def test_min_wall_thickness_horizontal_corridor_across_cube():
    """Restrict region to a thin horizontal slab to measure wall-to-wall gap.

    A 10x10 cube section at Z=5: a region [(-1,0),(1,10)] cuts across the
    cube horizontally, so the closest points are on the bottom and top edges
    at y=0 and y=10 — distance 10mm.
    """
    cube = _solid_cube(size=10.0)
    result = min_wall_thickness_at_z(
        cube, z=5.0,
        region=((4.5, 0.0), (5.5, 10.0)),  # narrow vertical strip
    )
    assert result["ok"] is True
    assert result["min_thickness_mm"] == pytest.approx(10.0, abs=1.0)


def test_min_wall_thickness_no_intersection():
    cube = _solid_cube(size=10.0)
    result = min_wall_thickness_at_z(cube, z=20.0)  # outside the cube
    assert result["ok"] is False
