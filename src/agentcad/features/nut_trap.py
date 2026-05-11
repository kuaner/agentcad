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
    Locations,
    Mode,
    Part,
    Polygon,
    Rot,
    extrude,
)

from ..hardware.screws import Screw, screw

if TYPE_CHECKING:
    from .contract import ContractBuilder


def _hexagon_vertices(radius: float) -> list[tuple[float, float]]:
    """Regular hexagon vertices for a given circumradius (across-flats / 2)."""
    # Across-flats radius → across-corners circumradius
    cr = radius / math.cos(math.radians(30))
    return [
        (cr * math.cos(math.radians(60 * i)), cr * math.sin(math.radians(60 * i)))
        for i in range(6)
    ]


def nut_trap(
    spec: str | Screw,
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
    s = screw(spec) if isinstance(spec, str) else spec
    cx, cy = center

    # Hex nut dimensions: across-flats ≈ 2×nominal_diameter for M3–M8
    # Standard: AF = 5.5 for M3, 7 for M4, 8 for M5, 10 for M6, 13 for M8
    af_map = {2.0: 4.0, 2.5: 5.0, 3.0: 5.5, 4.0: 7.0, 5.0: 8.0, 6.0: 10.0, 8.0: 13.0}
    af = af_map.get(s.nominal_diameter, s.nominal_diameter * 1.8)
    hex_r = af / 2

    # Hex pocket
    with BuildPart(mode=Mode.PRIVATE) as bp:
        with BuildSketch():
            Polygon(_hexagon_vertices(hex_r))
        extrude(amount=depth)

        # Side-entry slot: rectangular opening on one side
        if orientation == "side" and entry_slot_width > 0:
            slot_height = af
            with Locations((0, hex_r + slot_height / 2, depth / 2)):
                # Slot as a box: extends outward from hex face
                # Width = entry_slot_width along Z, height along Y, depth along X
                # Actually, use a simple rectangular cut through one face
                pass  # Slot is added via separate subtraction

    result = bp.part.moved(Location((cx, cy, base_z)))

    # Add entry slot as separate geometry
    if orientation == "side" and entry_slot_width > 0:
        with BuildPart(mode=Mode.PRIVATE) as slot_bp:
            with BuildSketch():
                from build123d import Rectangle
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
                "description": f"nut_trap {s.name} depth={depth}mm orient={orientation}",
            },
            checks=checks,
        )

    return result