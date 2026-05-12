"""Tube helper: hollow cylinder (sleeve, bushing, spacer)."""
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


def tube(
    outer_diameter: float,
    inner_diameter: float,
    height: float,
    *,
    center: tuple[float, float] = (0.0, 0.0),
    base_z: float = 0.0,
    fillet_r: float = 0.0,
    builder: ContractBuilder | None = None,
    feature_id: str = "tube",
) -> Part:
    """Create a hollow cylinder (tube).

    Parameters
    ----------
    outer_diameter : float
        Outer diameter (mm).
    inner_diameter : float
        Inner diameter (mm).
    height : float
        Tube height (mm).
    center : tuple[float, float]
        XY center position.
    base_z : float
        Z position of the tube base.
    fillet_r : float
        Optional fillet radius on outer edges.
    builder : ContractBuilder | None
        If provided, registers feature and checks.
    feature_id : str
        Base ID for entries.

    Returns
    -------
    Part
        The hollow cylinder.
    """
    cx, cy = center
    outer_r = outer_diameter / 2
    inner_r = inner_diameter / 2

    with BuildPart(mode=Mode.PRIVATE) as bp:
        Cylinder(
            radius=outer_r, height=height,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )
        Cylinder(
            radius=inner_r, height=height,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
            mode=Mode.SUBTRACT,
        )
        if fillet_r > 0:
            from build123d import fillet, edges_by_predicate
            fillet(bp.edges(), radius=fillet_r)

    result = bp.part.moved(Location((cx, cy, base_z)))

    if builder is not None:
        mid_z = base_z + height / 2
        checks = [
            {
                "id": f"{feature_id}_outer",
                "type": "outer_diameter_at_z",
                "z": mid_z,
                "center": [cx, cy],
                "expected": outer_diameter,
                "tolerance": 0.5,
                "feature_ref": feature_id,
            },
            {
                "id": f"{feature_id}_inner",
                "type": "inner_diameter_at_z",
                "z": mid_z,
                "center": [cx, cy],
                "expected": inner_diameter,
                "tolerance": 0.3,
                "feature_ref": feature_id,
            },
        ]
        builder.add(
            feature={
                "id": feature_id,
                "description": f"tube OD={outer_diameter}mm ID={inner_diameter}mm h={height}mm",
            },
            checks=checks,
        )
        builder.add_interface(f"{feature_id}_outer_sleeve", {
            "kind": "cylindrical_male",
            "axis": {"point": [cx, cy, base_z], "direction": [0, 0, 1]},
            "outer_cylinder": {
                "type": "cylinder", "axis": "z", "center": [cx, cy],
                "radius": outer_r, "z_range": [base_z, base_z + height],
            },
        })
        builder.add_interface(f"{feature_id}_inner_bore", {
            "kind": "cylindrical_female",
            "axis": {"point": [cx, cy, base_z], "direction": [0, 0, 1]},
            "inner_cylinder": {
                "type": "cylinder", "axis": "z", "center": [cx, cy],
                "radius": inner_r, "z_range": [base_z, base_z + height],
            },
        })

    return result
