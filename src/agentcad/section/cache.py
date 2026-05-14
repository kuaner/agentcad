from __future__ import annotations

from ..stl import Triangle
from .analysis import analyze_section_segments
from .extraction import section_segments
from .types import Segment2D

class SectionCache:
    """Per-validation cache for triangle-plane intersections.

    Caches section segments and analyses keyed by mesh identity, axis, and
    position.
    Avoids recomputing the same cross-section when multiple checks
    slice the same position (e.g. diameter + component_count at Z=5).
    """

    def __init__(self) -> None:
        self._segments: dict[tuple[int, int, float], list[Segment2D]] = {}
        self._analysis: dict[tuple[int, int, float], dict] = {}

    def segments(self, triangles: list[Triangle], axis: int, position: float) -> list[Segment2D]:
        key = self._key(triangles, axis, position)
        if key not in self._segments:
            self._segments[key] = section_segments(triangles, axis, position)
        return self._segments[key]

    def analysis(self, triangles: list[Triangle], axis: int, position: float) -> dict:
        key = self._key(triangles, axis, position)
        if key not in self._analysis:
            segs = self.segments(triangles, axis, position)
            self._analysis[key] = analyze_section_segments(segs, axis, position)
        return self._analysis[key]

    @staticmethod
    def _key(triangles: list[Triangle], axis: int, position: float) -> tuple[int, int, float]:
        return (id(triangles), axis, round(position, 5))
