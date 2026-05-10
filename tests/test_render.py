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


def test_render_with_bbox_annotations():
    tris = [((0, 0, 0), (50, 0, 0), (0, 30, 0))]
    bbox = {"min": [0, 0, 0], "max": [50, 30, 20], "size": [50.0, 30.0, 20.0], "center": [25, 15, 10]}
    svg = triangles_to_svg(tris, title="annotated", view="front", bbox=bbox)
    assert 'id="annotations"' in svg
    assert "50.0 mm" in svg
    assert "20.0 mm" in svg


def test_render_without_bbox_no_annotations():
    tris = [((0, 0, 0), (10, 0, 0), (0, 10, 0))]
    svg = triangles_to_svg(tris, title="plain", view="iso")
    assert 'id="annotations"' not in svg


def test_render_axis_labels_per_view():
    bbox = {"min": [0, 0, 0], "max": [10, 20, 30], "size": [10.0, 20.0, 30.0], "center": [5, 10, 15]}
    tris = [((0, 0, 0), (10, 0, 0), (0, 10, 0))]

    front = triangles_to_svg(tris, view="front", bbox=bbox)
    assert "(X)" in front
    assert "(Z)" in front

    top = triangles_to_svg(tris, view="top", bbox=bbox)
    assert "(X)" in top
    assert "(Y)" in top

    side = triangles_to_svg(tris, view="side", bbox=bbox)
    assert "(Y)" in side
    assert "(Z)" in side
