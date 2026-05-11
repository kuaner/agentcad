"""Boss helper: raised cylinder with auto-emitting clearance checks."""
from __future__ import annotations

from typing import TYPE_CHECKING

from build123d import (
    Align,
    BuildPart,
    Cylinder,
    Location,
    Mode,
    Part,
)

if TYPE_CHECKING:
    from .contract import ContractBuilder


def boss(
    diameter: float,
    height: float,
    *,
    center: tuple[float, float] = (0.0, 0.0),
    base_z: float = 0.0,
    inner_diameter: float = 0.0,
    builder: ContractBuilder | None = None,
    feature_id: str = "boss",
) -> Part:
    """Create a raised boss (cylindrical) with optional through-hole.

    Parameters
    ----------
    diameter : float
        Outer diameter of the boss (mm).
    height : float
        Boss height (mm).
    center : tuple[float, float]
        XY center position.
    base_z : float
        Z position of the boss base.
    inner_diameter : float
        If > 0, creates a through-hole and adds inner_diameter check.
    builder : ContractBuilder | None
        If provided, registers feature and checks.
    feature_id : str
        Base ID for entries.

    Returns
    -------
    Part
        The boss solid (or hollow boss if inner_diameter > 0).
    """
    cx, cy = center
    radius = diameter / 2
    inner_r = inner_diameter / 2 if inner_diameter > 0 else 0

    with BuildPart(mode=Mode.PRIVATE) as bp:
        Cylinder(radius=radius, height=height,
                 align=(Align.CENTER, Align.CENTER, Align.MIN))
        if inner_r > 0:
            Cylinder(radius=inner_r, height=height,
                     align=(Align.CENTER, Align.CENTER, Align.MIN),
                     mode=Mode.SUBTRACT)
    result = bp.part.moved(Location((cx, cy, base_z)))

    if builder is not None:
        checks: list[dict] = []
        if inner_diameter > 0:
            checks.append({
                "id": f"{feature_id}_hole",
                "type": "inner_diameter_at_z",
                "z": base_z + height / 2,
                "center": [cx, cy],
                "expected": inner_diameter,
                "tolerance": 0.3,
                "feature_ref": feature_id,
            })
        builder.add(
            feature={
                "id": feature_id,
                "description": f"boss OD={diameter}mm h={height}mm" +
                               (f" ID={inner_diameter}mm" if inner_diameter > 0 else ""),
            },
            checks=checks,
        )

    return result
