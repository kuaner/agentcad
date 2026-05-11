"""Mounting pattern helper: bolt hole patterns with auto-emitting checks.

Generates holes and matching inner_diameter + hole_accessibility checks
based on hardware specs from the hardware database.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Literal

from build123d import (
    Align,
    BuildPart,
    Cylinder,
    Location,
    Mode,
    Part,
)

from ..hardware.screws import Screw, screw

if TYPE_CHECKING:
    from .contract import ContractBuilder

PatternKind = Literal["square", "rectangular", "linear", "circular"]


def mounting_pattern(
    spec: str | Screw,
    *,
    kind: PatternKind = "square",
    spacing: float | None = None,
    spacing_x: float | None = None,
    spacing_y: float | None = None,
    count: int | None = None,
    center: tuple[float, float] = (0.0, 0.0),
    depth: float = 5.0,
    through: bool = True,
    fit: str = "normal",
    approach_axis: str = "z",
    approach_z: float | None = None,
    builder: ContractBuilder | None = None,
    feature_id: str = "mounting_holes",
) -> Part:
    """Create a bolt hole pattern and optionally register hole checks."""
    s = screw(spec) if isinstance(spec, str) else spec
    hole_radius = s.clearance_radius if through else s.tap_radius
    hole_diameter = hole_radius * 2

    positions = _compute_positions(kind, spacing, spacing_x, spacing_y, count, center)

    holes = []
    for px, py in positions:
        with BuildPart(mode=Mode.PRIVATE) as hole:
            Cylinder(
                radius=hole_radius,
                height=depth,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )
        holes.append(hole.part.moved(Location((px, py, 0))))

    result = holes[0]
    for h in holes[1:]:
        result = result.fuse(h)

    if builder is not None:
        checks: list[dict] = []
        for i, (px, py) in enumerate(positions):
            suffix = f"_{i}" if len(positions) > 1 else ""
            checks.append({
                "id": f"{feature_id}_dia{suffix}",
                "type": "inner_diameter_at_z",
                "z": depth / 2,
                "center": [px, py],
                "expected": hole_diameter,
                "tolerance": 0.3,
                "feature_ref": feature_id,
            })
            if through:
                z_check = approach_z if approach_z is not None else depth + 0.5
                checks.append({
                    "id": f"{feature_id}_access{suffix}",
                    "type": "hole_accessibility",
                    "z": z_check,
                    "center": [px, py],
                    "hole_diameter": hole_diameter,
                    "clearance_diameter": s.head_diameter + 1.0,
                    "approach_axis": approach_axis,
                    "feature_ref": feature_id,
                })

        builder.add(
            feature={
                "id": feature_id,
                "description": f"{s.name} {kind} pattern, {len(positions)} holes, spacing {spacing or spacing_x}mm",
            },
            checks=checks,
        )

    return result


def _compute_positions(
    kind: PatternKind,
    spacing: float | None,
    spacing_x: float | None,
    spacing_y: float | None,
    count: int | None,
    center: tuple[float, float],
) -> list[tuple[float, float]]:
    cx, cy = center
    if kind == "square":
        sp = spacing or 0
        if sp <= 0:
            raise ValueError("square pattern requires spacing > 0")
        half = sp / 2
        return [
            (cx - half, cy - half),
            (cx + half, cy - half),
            (cx - half, cy + half),
            (cx + half, cy + half),
        ]
    elif kind == "rectangular":
        sx = spacing_x or spacing or 0
        sy = spacing_y or spacing or 0
        if sx <= 0 or sy <= 0:
            raise ValueError("rectangular pattern requires spacing_x, spacing_y > 0")
        return [
            (cx - sx / 2, cy - sy / 2),
            (cx + sx / 2, cy - sy / 2),
            (cx - sx / 2, cy + sy / 2),
            (cx + sx / 2, cy + sy / 2),
        ]
    elif kind == "linear":
        sp = spacing or 0
        n = count or 2
        if sp <= 0:
            raise ValueError("linear pattern requires spacing > 0")
        total = (n - 1) * sp
        start = cx - total / 2
        return [(start + i * sp, cy) for i in range(n)]
    elif kind == "circular":
        sp = spacing or 0
        n = count or 4
        radius = sp / 2 if sp > 0 else 0
        if radius <= 0:
            raise ValueError("circular pattern requires spacing (diameter) > 0")
        return [
            (cx + radius * math.cos(2 * math.pi * i / n),
             cy + radius * math.sin(2 * math.pi * i / n))
            for i in range(n)
        ]
    else:
        raise ValueError(f"unknown pattern kind: {kind!r}")
