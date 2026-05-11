"""Rounding mask helper: edge roundover/fillet (subtract from edges)."""
from __future__ import annotations

import math

from typing import TYPE_CHECKING, Literal

from build123d import (
    BuildPart,
    BuildSketch,
    Location,
    Mode,
    Part,
    Polygon,
    Rot,
    extrude,
)

if TYPE_CHECKING:
    from .contract import ContractBuilder


def _rounding_profile(size: float, n_pts: int = 12) -> list[tuple[float, float]]:
    """Quarter-circle arc profile from (0,0) to (size,0) to (0,size).

    Creates a filled region bounded by the arc and two legs back to the origin.
    """
    arc_pts = []
    for i in range(n_pts + 1):
        angle = math.pi / 2 * i / n_pts
        arc_pts.append((size * math.cos(angle), size * math.sin(angle)))
    return [(0, 0), (size, 0)] + arc_pts[1:-1] + [(0, size)]


def rounding_mask(
    length: float,
    *,
    edge: Literal["x", "y", "z"] = "z",
    size: float = 1.0,
    builder: ContractBuilder | None = None,
    feature_id: str = "rounding",
) -> Part:
    """Create a rounding/fillet mask to subtract from edges.

    Returns a solid with a quarter-circle profile that can be subtracted
    from a part to create a rounded edge.  The mask is positioned so its
    flat faces sit against the two adjacent faces and the curved face
    creates the fillet.

    Parameters
    ----------
    length : float
        Fillet length along the edge axis (mm).
    edge : str
        Which axis the fillet runs along: ``"x"``, ``"y"``, or ``"z"``.
    size : float
        Fillet radius — the radius of the quarter-circle arc (mm).
    builder : ContractBuilder | None
        If provided, registers feature and checks.
    feature_id : str
        Base ID for entries.

    Returns
    -------
    Part
        The rounding mask solid (subtract from your part).
    """
    if edge not in ("x", "y", "z"):
        raise ValueError(f"edge must be 'x', 'y', or 'z', got '{edge}'")

    profile = _rounding_profile(size)

    with BuildPart(mode=Mode.PRIVATE) as bp:
        with BuildSketch():
            Polygon(profile)
        extrude(amount=length)

    part = bp.part

    if edge == "z":
        result = part
    elif edge == "x":
        result = part.moved(Rot(90, 0, 0))
    elif edge == "y":
        result = part.moved(Rot(0, 90, 0))

    if builder is not None:
        builder.add(
            feature={
                "id": feature_id,
                "description": f"rounding_mask radius={size}mm edge={edge} length={length}mm",
            },
            checks=[],
        )

    return result