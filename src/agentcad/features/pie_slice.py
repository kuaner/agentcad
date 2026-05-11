"""Pie slice helper: cylindrical sector wedge."""
from __future__ import annotations

import math

from typing import TYPE_CHECKING

from build123d import (
    Align,
    BuildPart,
    BuildSketch,
    Cylinder,
    Location,
    Mode,
    Part,
    Polygon,
    extrude,
)

if TYPE_CHECKING:
    from .contract import ContractBuilder


def _sector_polygon(radius: float, angle: float, n_arc: int = 20) -> list[tuple[float, float]]:
    """Build a sector polygon: arc from angle=0 to angle, plus two radii to center."""
    pts = [(0, 0)]
    for i in range(n_arc + 1):
        a = angle * i / n_arc
        pts.append((radius * math.cos(math.radians(a)), radius * math.sin(math.radians(a))))
    pts.append((0, 0))
    return pts


def pie_slice(
    radius: float,
    angle: float,
    height: float,
    *,
    center: tuple[float, float] = (0.0, 0.0),
    base_z: float = 0.0,
    builder: ContractBuilder | None = None,
    feature_id: str = "pie_slice",
) -> Part:
    """Create a cylindrical sector (pie slice wedge).

    Parameters
    ----------
    radius : float
        Outer radius of the sector (mm).
    angle : float
        Sector angle in degrees (mm). Full circle = 360.
    height : float
        Height along Z (mm).
    center : tuple[float, float]
        XY center position (center of the arc).
    base_z : float
        Z position of the base.
    builder : ContractBuilder or None
        If provided, registers feature and checks.
    feature_id : str
        Base ID for entries.

    Returns
    -------
    Part
        The pie slice sector.
    """
    if radius <= 0:
        raise ValueError(f"radius must be > 0, got {radius}")
    if angle <= 0 or angle > 360:
        raise ValueError(f"angle must be in (0, 360], got {angle}")
    if height <= 0:
        raise ValueError(f"height must be > 0, got {height}")

    cx, cy = center

    if angle == 360:
        with BuildPart(mode=Mode.PRIVATE) as bp:
            Cylinder(radius=radius, height=height, align=(Align.CENTER, Align.CENTER, Align.MIN))
    else:
        profile = _sector_polygon(radius, angle)
        with BuildPart(mode=Mode.PRIVATE) as bp:
            with BuildSketch():
                Polygon(profile)
            extrude(amount=height)

    result = bp.part.moved(Location((cx, cy, base_z)))

    if builder is not None:
        bbox_w = radius * 2
        builder.add(
            feature={
                "id": feature_id,
                "description": f"pie_slice r={radius} angle={angle}° h={height}mm",
            },
            checks=[
                {
                    "id": f"{feature_id}_bbox",
                    "type": "bbox_size",
                    "expected": [bbox_w, radius * 2, height],
                    "tolerance": 1.0,
                    "feature_ref": feature_id,
                },
                {
                    "id": f"{feature_id}_volume",
                    "type": "volume_range",
                    "min": 0,
                    "max": math.pi * radius**2 * height,
                    "feature_ref": feature_id,
                },
            ],
        )

    return result