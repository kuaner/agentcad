"""Nut trap helper: hex pocket for nut retention."""
from __future__ import annotations

import math

from typing import TYPE_CHECKING, Literal

from build123d import (
    Align,
    BuildPart,
    BuildSketch,
    Cylinder,
    Location,
    Mode,
    Part,
    Polygon,
    Rectangle,
    extrude,
)

from ..hardware.nuts import Nut, nut as nut_lookup
from ._geometry import hexagon_vertices

if TYPE_CHECKING:
    from .contract import ContractBuilder


def nut_trap(
    spec: str | Nut,
    *,
    depth: float = 10.0,
    orientation: Literal["side", "top"] = "side",
    entry_slot_width: float = 0.0,
    center: tuple[float, float] = (0.0, 0.0),
    base_z: float = 0.0,
    builder: ContractBuilder | None = None,
    feature_id: str = "nut_trap",
) -> Part:
    """Create a hex nut trap pocket (negative solid).

    Subtract this from your part to create a pocket that holds a hex
    nut.  For side-entry traps, a slot allows the nut to be slid in
    from the side.

    Parameters
    ----------
    spec : str | Screw
        Screw spec like ``"M3"`` — used to determine nut size.
    depth : float
        Pocket depth (mm).
    orientation : str
        ``"side"`` — nut slides in from the side (entry slot optional).
        ``"top"`` — nut drops in from the top.
    entry_slot_width : float
        Width of the side-entry slot (mm).  0 means no slot.
    center : tuple[float, float]
        XY center position.
    base_z : float
        Z position of the pocket base.
    builder : ContractBuilder | None
        If provided, registers feature and checks.
    feature_id : str
        Base ID for entries.

    Returns
    -------
    Part
        The hex pocket solid (subtract from your part).
    """
    n = nut_lookup(spec) if isinstance(spec, str) else spec
    cx, cy = center

    af = n.width_across_flats
    hex_r = af / 2

    # Hex pocket
    with BuildPart(mode=Mode.PRIVATE) as bp:
        with BuildSketch():
            Polygon(hexagon_vertices(hex_r / math.cos(math.radians(30)), rotation=0))
        extrude(amount=depth)

    result = bp.part.moved(Location((cx, cy, base_z)))

    # Add entry slot as separate geometry
    if orientation == "side" and entry_slot_width > 0:
        with BuildPart(mode=Mode.PRIVATE) as slot_bp:
            with BuildSketch():
                Rectangle(entry_slot_width, af)
            extrude(amount=depth)
        slot = slot_bp.part.moved(Location((cx, cy + hex_r + af / 2, base_z)))
        result = result.fuse(slot)

    if builder is not None:
        mid_z = base_z + depth / 2
        checks = [
            {
                "id": f"{feature_id}_hex",
                "type": "section_bbox_at_z",
                "z": mid_z,
                "center": [cx, cy],
                "expected_max": [af * 0.6, af * 0.6],
                "tolerance": 0.5,
                "feature_ref": feature_id,
            },
        ]
        builder.add(
            feature={
                "id": feature_id,
                "description": f"nut_trap {n.name} depth={depth}mm orient={orientation}",
            },
            checks=checks,
        )

    return result