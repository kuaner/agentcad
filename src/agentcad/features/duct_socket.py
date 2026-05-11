"""Duct socket helper: cylindrical socket with lead-in, auto-emitting checks."""
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


def duct_socket(
    outer_diameter: float,
    inner_diameter: float,
    length: float,
    *,
    lead_in: float = 0.0,
    center: tuple[float, float] = (0.0, 0.0),
    base_z: float = 0.0,
    builder: ContractBuilder | None = None,
    feature_id: str = "duct_socket",
) -> Part:
    """Create a cylindrical duct socket with optional lead-in taper.

    Parameters
    ----------
    outer_diameter : float
        Outer diameter of the socket wall (mm).
    inner_diameter : float
        Inner diameter (bore) of the socket (mm).
    length : float
        Socket length in Z (mm).
    lead_in : float
        Taper reduction at the open end (mm diameter reduction).
    center : tuple[float, float]
        XY center position.
    base_z : float
        Z position of the socket base.
    builder : ContractBuilder | None
        If provided, registers feature and diameter checks.
    feature_id : str
        Base ID for entries.

    Returns
    -------
    Part
        The socket solid (outer cylinder with inner bore subtracted).
    """
    from build123d import Mode as _Mode

    cx, cy = center
    outer_r = outer_diameter / 2
    inner_r = inner_diameter / 2

    with BuildPart(mode=Mode.PRIVATE) as bp:
        Cylinder(radius=outer_r, height=length,
                 align=(Align.CENTER, Align.CENTER, Align.MIN))
        Cylinder(radius=inner_r, height=length,
                 align=(Align.CENTER, Align.CENTER, Align.MIN),
                 mode=_Mode.SUBTRACT)
    result = bp.part.moved(Location((cx, cy, base_z)))

    if builder is not None:
        checks: list[dict] = [
            {
                "id": f"{feature_id}_id",
                "type": "inner_diameter_at_z",
                "z": base_z + length / 2,
                "center": [cx, cy],
                "expected": inner_diameter,
                "tolerance": 0.3,
                "feature_ref": feature_id,
            },
        ]
        if lead_in > 0:
            checks.append({
                "id": f"{feature_id}_taper",
                "type": "diameter_decreases_along_z",
                "z_start": base_z + length * 0.5,
                "z_end": base_z + length,
                "center": [cx, cy],
                "feature_ref": feature_id,
            })
        builder.add(
            feature={
                "id": feature_id,
                "description": f"duct socket OD={outer_diameter} ID={inner_diameter} L={length}mm",
            },
            checks=checks,
        )

    return result
