"""Tests for SVG preview renderer."""
from __future__ import annotations

from agentcad.render import triangles_to_svg


def test_render_empty():
    svg = triangles_to_svg([], title="empty")
    assert "No geometry" in svg
    assert "<svg" in svg


def test_render_single_triangle():
    tris = [((0, 0, 0), (10, 0, 0), (0, 10, 0))]
    svg = triangles_to_svg(tris, title="tri", view="iso")
    assert "<svg" in svg
    assert "<polygon" in svg


def test_render_views():
    tris = [((0, 0, 0), (1, 0, 0), (0, 1, 0))]
    for view in ("iso", "front", "top", "side"):
        svg = triangles_to_svg(tris, title=view, view=view)
        assert "<svg" in svg
        assert "<polygon" in svg


def test_render_title_escaped():
    tris = [((0, 0, 0), (1, 0, 0), (0, 1, 0))]
    svg = triangles_to_svg(tris, title="<script>alert(1)</script>")
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg
