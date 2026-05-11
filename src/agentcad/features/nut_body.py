"""Nut body helper: hex nut 3D solid for assembly visualization."""
from __future__ import annotations

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

from ..hardware.nuts import Nut, nut as nut_lookup
from ._geometry import hexagon_vertices

if TYPE_CHECKING:
    from .contract import ContractBuilder


def nut_body(
    spec: str | Nut = "M3",
    *,
    center: tuple[float, float] = (0.0, 0.0),
    base_z: float = 0.0,
    builder: ContractBuilder | None = None,
    feature_id: str = "nut",
) -> Part:
    """Create a hex nut 3D solid for assembly visualization.

    Returns a positive solid hex nut (not a subtractive pocket).
    Use this for visualizing hardware in assemblies, not for
    creating nut traps (use ``nut_trap`` for that).

    Parameters
    ----------
    spec : str or Nut
        Nut specification like "M3", "M4". Uses hardware dimensions.
    center : tuple[float, float]
        XY center position.
    base_z : float
        Z position of the base.
    builder : ContractBuilder or None
        If provided, registers feature and checks.
    feature_id : str
        Base ID for entries.

    Returns
    -------
    Part
        The hex nut solid.
    """
    n = nut_lookup(spec) if isinstance(spec, str) else spec
    corner_r = n.width_across_corners / 2
    thickness = n.thickness
    bore_d = n.screw_diameter

    cx, cy = center

    hex_verts = hexagon_vertices(corner_r)

    with BuildPart(mode=Mode.PRIVATE) as bp:
        # Hex body
        with BuildSketch():
            Polygon(hex_verts)
        extrude(amount=thickness)

        # Thread bore
        Cylinder(
            radius=bore_d / 2,
            height=thickness + 1,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
            mode=Mode.SUBTRACT,
        ).moved(Location((0, 0, -0.5)))

    result = bp.part.moved(Location((cx, cy, base_z)))

    if builder is not None:
        builder.add(
            feature={
                "id": feature_id,
                "description": f"nut {n.name} bore={bore_d}mm h={thickness}mm",
            },
            checks=[
                {
                    "id": f"{feature_id}_section",
                    "type": "section_bbox_at_z",
                    "z": base_z + thickness / 2,
                    "center": [cx, cy],
                    "expected_max": [corner_r, corner_r],
                    "tolerance": 0.5,
                    "feature_ref": feature_id,
                },
                {
                    "id": f"{feature_id}_bore",
                    "type": "inner_diameter_at_z",
                    "z": base_z + thickness / 2,
                    "center": [cx, cy],
                    "expected": bore_d,
                    "tolerance": 0.5,
                    "feature_ref": feature_id,
                },
            ],
        )

    return result