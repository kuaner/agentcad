"""Teardrop helper: FDM-printable horizontal hole shape."""
from __future__ import annotations

import math

from typing import TYPE_CHECKING

from build123d import (
    BuildPart,
    BuildSketch,
    Location,
    Mode,
    Part,
    Rot,
    Circle,
    Polygon,
    extrude,
)

if TYPE_CHECKING:
    from .contract import ContractBuilder


def teardrop(
    diameter: float,
    height: float,
    *,
    angle: float = 45.0,
    center: tuple[float, float] = (0.0, 0.0),
    base_z: float = 0.0,
    builder: ContractBuilder | None = None,
    feature_id: str = "teardrop",
) -> Part:
    """Create a teardrop-shaped negative solid for FDM-printable holes.

    Horizontal round holes in FDM prints need overhang support.  A
    teardrop cross-section (semicircle below + tapered tip above) keeps
    the overhang angle at ``angle`` degrees from vertical, making the
    hole printable without support material.

    This returns a **positive solid** shaped like the teardrop.  To use
    it as a hole, subtract it from your part via
    ``add(teardrop(...), mode=Mode.SUBTRACT)`` inside a ``BuildPart``.

    Parameters
    ----------
    diameter : float
        Hole diameter (mm).
    height : float
        Extrusion length / hole depth (mm).
    angle : float
        Overhang angle from vertical in degrees (default 45).
    center : tuple[float, float]
        XY center position.
    base_z : float
        Z position of the base.
    builder : ContractBuilder | None
        If provided, registers feature and checks.
    feature_id : str
        Base ID for entries.

    Returns
    -------
    Part
        The teardrop-shaped solid (subtract from part to make a hole).
    """
    cx, cy = center
    r = diameter / 2

    # Tip extends above the circle top by r / cos(90 - angle)
    tip_height = r / math.cos(math.radians(90 - angle))

    # Build 2D teardrop profile: circle + triangle tip
    with BuildPart(mode=Mode.PRIVATE) as bp:
        with BuildSketch():
            Circle(r)
            # Triangle above the circle: flat top of circle at Y=r,
            # tip at Y=r + tip_height
            # Angle from vertical means tip width at circle top
            tip_width = r * math.sin(math.radians(90 - angle))
            Polygon([
                (-tip_width, r),
                (tip_width, r),
                (0, r + tip_height),
            ])
        extrude(amount=height)

    result = bp.part.moved(Rot(-90, 0, 0)).moved(Location((cx, cy, base_z)))

    if builder is not None:
        mid_z = base_z + height / 2
        builder.add(
            feature={
                "id": feature_id,
                "description": f"teardrop d={diameter}mm h={height}mm angle={angle}deg",
            },
            checks=[
                {
                    "id": f"{feature_id}_inner",
                    "type": "inner_diameter_at_z",
                    "z": mid_z,
                    "center": [cx, cy],
                    "expected": diameter,
                    "tolerance": 0.5,
                    "feature_ref": feature_id,
                },
            ],
        )

    return result