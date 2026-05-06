"""Tests for STL reader, mesh report, and section checks."""
from __future__ import annotations

import struct

from agentcad.stl import (
    cross,
    dot,
    length,
    mesh_report,
    normalize,
    read_stl,
    section_radius_at_z,
    sub,
    triangle_area,
    triangle_normal,
)


def _make_binary_stl(triangles):
    """Build a binary STL byte buffer from a list of triangles."""
    buf = bytearray(80)  # header
    buf += struct.pack("<I", len(triangles))
    for tri in triangles:
        buf += struct.pack("<3f", 0.0, 0.0, 1.0)  # normal
        for v in tri:
            buf += struct.pack("<3f", *v)
        buf += struct.pack("<H", 0)  # attribute
    return bytes(buf)


def _single_triangle_stl():
    tri = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    return _make_binary_stl([tri])


def _cube_stl():
    """A unit cube at origin."""
    verts = [
        (0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
        (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1),
    ]
    faces = [
        (0, 1, 2), (0, 2, 3),  # bottom
        (4, 6, 5), (4, 7, 6),  # top
        (0, 5, 1), (0, 4, 5),  # front
        (2, 7, 3), (2, 6, 7),  # back
        (0, 3, 7), (0, 7, 4),  # left
        (1, 5, 6), (1, 6, 2),  # right
    ]
    tris = [(verts[i], verts[j], verts[k]) for i, j, k in faces]
    return _make_binary_stl(tris)


def _cylinder_stl(radius=5.0, height=10.0, segments=24, offset=(0.0, 0.0)):
    """Approximate cylinder centered at offset, Z from 0 to height."""
    ox, oy = offset
    triangles = []
    for i in range(segments):
        a0 = 2 * 3.14159265358979 * i / segments
        a1 = 2 * 3.14159265358979 * (i + 1) / segments
        x0, y0 = radius * __import__("math").cos(a0) + ox, radius * __import__("math").sin(a0) + oy
        x1, y1 = radius * __import__("math").cos(a1) + ox, radius * __import__("math").sin(a1) + oy
        # bottom cap
        triangles.append(((ox, oy, 0), (x1, y1, 0), (x0, y0, 0)))
        # top cap
        triangles.append(((ox, oy, height), (x0, y0, height), (x1, y1, height)))
        # side
        triangles.append(((x0, y0, 0), (x1, y1, 0), (x1, y1, height)))
        triangles.append(((x0, y0, 0), (x1, y1, height), (x0, y0, height)))
    return _make_binary_stl(triangles)


# --- Vector math ---

def test_sub():
    assert sub((3, 2, 1), (1, 1, 1)) == (2, 1, 0)


def test_dot():
    assert dot((1, 0, 0), (0, 1, 0)) == 0
    assert dot((1, 0, 0), (1, 0, 0)) == 1


def test_cross():
    assert cross((1, 0, 0), (0, 1, 0)) == (0, 0, 1)


def test_length():
    assert length((3, 4, 0)) == 5.0


def test_normalize():
    n = normalize((0, 0, 3))
    assert abs(n[2] - 1.0) < 1e-9
    assert normalize((0, 0, 0))[2] == 1.0  # fallback


# --- STL reading ---

def test_read_binary_stl(tmp_path):
    p = tmp_path / "test.stl"
    p.write_bytes(_single_triangle_stl())
    tris = read_stl(p)
    assert len(tris) == 1
    assert len(tris[0]) == 3


def test_read_ascii_stl(tmp_path):
    ascii_stl = (
        "solid test\n"
        "  facet normal 0 0 1\n"
        "    outer loop\n"
        "      vertex 0 0 0\n"
        "      vertex 1 0 0\n"
        "      vertex 0 1 0\n"
        "    endloop\n"
        "  endfacet\n"
        "endsolid test\n"
    )
    p = tmp_path / "test.stl"
    p.write_text(ascii_stl)
    tris = read_stl(p)
    assert len(tris) == 1


# --- Mesh report ---

def test_mesh_report_empty():
    report = mesh_report([])
    assert report["bbox"] is None
    assert report["mesh"]["triangles"] == 0


def test_mesh_report_single_triangle():
    tri = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
    report = mesh_report([tri])
    assert report["mesh"]["triangles"] == 1
    assert abs(report["bbox"]["size"][0] - 1.0) < 1e-6
    assert abs(report["bbox"]["size"][1] - 1.0) < 1e-6


def test_mesh_report_cube_watertight():
    p = tmp_path if "tmp_path" in dir() else None
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as td:
        stl_path = pathlib.Path(td) / "cube.stl"
        stl_path.write_bytes(_cube_stl())
        tris = read_stl(stl_path)
    report = mesh_report(tris)
    assert report["mesh"]["triangles"] == 12
    assert report["mesh"]["watertight"] is True
    for i in range(3):
        assert abs(report["bbox"]["size"][i] - 1.0) < 1e-6


def test_mesh_report_cube_volume():
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as td:
        stl_path = pathlib.Path(td) / "cube.stl"
        stl_path.write_bytes(_cube_stl())
        tris = read_stl(stl_path)
    report = mesh_report(tris)
    assert abs(report["mass_properties"]["volume"] - 1.0) < 0.01


# --- Section checks ---

def test_section_radius_cylinder():
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as td:
        stl_path = pathlib.Path(td) / "cyl.stl"
        stl_path.write_bytes(_cylinder_stl(radius=5.0, height=10.0, segments=48))
        tris = read_stl(stl_path)
    section = section_radius_at_z(tris, z=5.0, center=(0.0, 0.0))
    assert section["ok"] is True
    assert abs(section["diameter_outer_estimate"] - 10.0) < 0.5


def test_section_radius_empty():
    tri = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
    section = section_radius_at_z([tri], z=10.0)
    assert section["ok"] is False


def test_section_radius_off_axis():
    """Cylinder centered at (30, 20) — inner_diameter_at_z with matching center."""
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as td:
        stl_path = pathlib.Path(td) / "off_axis.stl"
        stl_path.write_bytes(_cylinder_stl(radius=5.0, height=10.0, segments=48, offset=(30.0, 20.0)))
        tris = read_stl(stl_path)
    # With center at the cylinder position → detects the hole
    section = section_radius_at_z(tris, z=5.0, center=(30.0, 20.0))
    assert section["ok"] is True
    assert abs(section["diameter_inner_estimate"] - 10.0) < 0.5
    # With center at origin → no hole, large inner diameter
    section_origin = section_radius_at_z(tris, z=5.0, center=(0.0, 0.0))
    assert section_origin["ok"] is True
    assert section_origin["diameter_inner_estimate"] > 30.0
