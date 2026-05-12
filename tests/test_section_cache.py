"""Tests for P4.2 SectionCache: caching triangle-plane intersections."""
from __future__ import annotations

from agentcad.section import SectionCache, section_segments, analyze_section_segments, AXIS_Z
from agentcad.stl import Triangle


def _box_triangles() -> list[Triangle]:
    """Return triangles for a simple 10x10x10 box centered at origin."""
    # Minimal box: 8 vertices, 12 triangles.
    v = [
        (-5, -5, -5), (5, -5, -5), (5, 5, -5), (-5, 5, -5),
        (-5, -5, 5), (5, -5, 5), (5, 5, 5), (-5, 5, 5),
    ]
    faces = [
        (0,1,2), (0,2,3),  # bottom
        (4,5,6), (4,6,7),  # top
        (0,1,5), (0,5,4),  # front
        (2,3,7), (2,7,6),  # back
        (0,3,7), (0,7,4),  # left
        (1,2,6), (1,6,5),  # right
    ]
    return [(v[a], v[b], v[c]) for a, b, c in faces]


class TestSectionCache:
    def test_segments_cached(self):
        tris = _box_triangles()
        cache = SectionCache()
        segs1 = cache.segments(tris, AXIS_Z, 0.0)
        segs2 = cache.segments(tris, AXIS_Z, 0.0)
        assert segs1 == segs2
        # Second call should hit cache, not recompute.
        # Verify by checking that the cache holds the key.
        assert (AXIS_Z, 0.0) in cache._segments

    def test_analysis_cached(self):
        tris = _box_triangles()
        cache = SectionCache()
        analysis1 = cache.analysis(tris, AXIS_Z, 0.0)
        analysis2 = cache.analysis(tris, AXIS_Z, 0.0)
        assert analysis1 == analysis2
        assert (AXIS_Z, 0.0) in cache._analysis

    def test_different_positions_not_shared(self):
        tris = _box_triangles()
        cache = SectionCache()
        segs0 = cache.segments(tris, AXIS_Z, 0.0)
        segs5 = cache.segments(tris, AXIS_Z, 5.0)
        # Both should produce results (box has sections at both Z positions).
        assert len(segs0) > 0
        assert len(segs5) > 0
        assert (AXIS_Z, 0.0) in cache._segments
        assert (AXIS_Z, 5.0) in cache._segments

    def test_rounding_avoids_duplicate_keys(self):
        tris = _box_triangles()
        cache = SectionCache()
        segs1 = cache.segments(tris, AXIS_Z, 0.000001)
        segs2 = cache.segments(tris, AXIS_Z, 0.000002)
        # Both round to 0.0 with 5 decimal places.
        assert (AXIS_Z, 0.0) in cache._segments
        # Only one key should exist for both calls.
        assert len(cache._segments) == 1

    def test_cache_matches_direct_computation(self):
        tris = _box_triangles()
        cache = SectionCache()
        cached_segs = cache.segments(tris, AXIS_Z, 0.0)
        direct_segs = section_segments(tris, AXIS_Z, 0.0)
        assert cached_segs == direct_segs

    def test_analysis_matches_direct_computation(self):
        tris = _box_triangles()
        cache = SectionCache()
        cached_analysis = cache.analysis(tris, AXIS_Z, 0.0)
        direct_segs = section_segments(tris, AXIS_Z, 0.0)
        direct_analysis = analyze_section_segments(direct_segs, AXIS_Z, 0.0)
        assert cached_analysis == direct_analysis

    def test_empty_cache_returns_empty_for_no_mesh(self):
        cache = SectionCache()
        segs = cache.segments([], AXIS_Z, 0.0)
        assert segs == []