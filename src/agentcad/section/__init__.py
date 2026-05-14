"""Cross-section extraction, measurement, and SVG rendering from STL meshes.

Slices a 3D mesh with an axis-aligned plane and returns either raw line
segments, structured numerical analysis, or an SVG for visual inspection.
"""
from __future__ import annotations

from .analysis import analyze_section_segments, scan_profile
from .cache import SectionCache
from .extraction import section_segments
from .measure import (
    measure_section_line,
    measure_section_point,
    measure_section_region,
    query_section_measurements,
)
from .render import _empty_svg, render_section_svg, write_section_svg
from .types import AXIS_X, AXIS_Y, AXIS_Z, Segment2D

__all__ = [
    "AXIS_X",
    "AXIS_Y",
    "AXIS_Z",
    "SectionCache",
    "Segment2D",
    "_empty_svg",
    "analyze_section_segments",
    "measure_section_line",
    "measure_section_point",
    "measure_section_region",
    "query_section_measurements",
    "render_section_svg",
    "scan_profile",
    "section_segments",
    "write_section_svg",
]
