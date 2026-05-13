"""Mounting pattern helper: bolt hole patterns with auto-emitting checks.

Generates hole positions and matching inner_diameter + hole_accessibility checks
based on hardware specs from the hardware database.

Usage within a BuildPart context::

    with BuildPart() as bp:
        plank = plate(...)
        add(plank)

        holes = MountingHoles(m5, kind="linear", spacing=40, count=2,
                              depth=base_thickness, builder=b)
        holes.cut()

Or get positions and cut manually::

    holes = MountingHoles(m5, kind="linear", spacing=40, count=2, depth=5)
    for px, py in holes.positions:
        with Locations((px, py, 0)):
            Cylinder(radius=holes.hole_radius, height=depth + 1,
                     align=(Align.CENTER, Align.CENTER, Align.MIN),
                     mode=Mode.SUBTRACT)
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Literal

from build123d import (
    Align,
    BuildPart,
    Cylinder,
    Location,
    Locations,
    Mode,
    Part,
)

from ..hardware.screws import Screw, screw

if TYPE_CHECKING:
    from .contract import ContractBuilder

PatternKind = Literal["square", "rectangular", "linear", "circular"]


class MountingHoles:
    """Bolt hole pattern with positions, geometry, and optional checks."""

    def __init__(
        self,
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
    ):
        s = screw(spec) if isinstance(spec, str) else spec
        self.hole_radius = s.clearance_radius if through else s.tap_radius
        self.hole_diameter = self.hole_radius * 2
        self.depth = depth
        self.screw = s
        self.through = through
        self.approach_axis = approach_axis
        self.approach_z = approach_z

        self.positions = _compute_positions(
            kind, spacing, spacing_x, spacing_y, count, center,
        )

        if builder is not None:
            checks: list[dict] = []
            for i, (px, py) in enumerate(self.positions):
                suffix = f"_{i}" if len(self.positions) > 1 else ""
                checks.append({
                    "id": f"{feature_id}_dia{suffix}",
                    "type": "inner_diameter_at_z",
                    "z": depth / 2,
                    "center": [px, py],
                    "expected": self.hole_diameter,
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
                        "hole_diameter": self.hole_diameter,
                        "clearance_diameter": s.head_diameter + 1.0,
                        "approach_axis": approach_axis,
                        "feature_ref": feature_id,
                    })

            builder.add(
                feature={
                    "id": feature_id,
                    "description": (
                        f"{s.name} {kind} pattern, "
                        f"{len(self.positions)} holes, "
                        f"spacing {spacing or spacing_x}mm"
                    ),
                },
                checks=checks,
            )
            builder.add_design_interface({
                "id": f"{feature_id}_fastener_pattern",
                "type": "fastener_clearance",
                "feature_ids": [feature_id],
                "access_axis": approach_axis,
                "failure_modes": ["hole_blocked", "edge_breakout"],
            })
            builder.add_failure_mode({
                "id": f"{feature_id}_edge_breakout",
                "mode": "edge_breakout",
                "severity": "high",
                "affects": [feature_id],
                "required_evidence": ["position", "dimensions", "access", "interface_risk"],
            })

    def cut(self) -> None:
        """Subtract holes from the active BuildPart context.

        Must be called inside a ``with BuildPart()`` block.
        Uses ``Locations`` + ``Cylinder(mode=SUBTRACT)`` for reliable
        boolean through-holes.
        """
        overshoot = 1.0
        for px, py in self.positions:
            with Locations((px, py, -overshoot / 2)):
                Cylinder(
                    radius=self.hole_radius,
                    height=self.depth + overshoot,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                    mode=Mode.SUBTRACT,
                )


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
) -> MountingHoles:
    """Backward-compatible factory: returns a MountingHoles instance."""
    return MountingHoles(
        spec,
        kind=kind, spacing=spacing, spacing_x=spacing_x, spacing_y=spacing_y,
        count=count, center=center, depth=depth, through=through, fit=fit,
        approach_axis=approach_axis, approach_z=approach_z,
        builder=builder, feature_id=feature_id,
    )


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
