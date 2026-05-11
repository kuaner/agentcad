"""Chamfer mask helper: edge chamfering (subtract from edges)."""
from __future__ import annotations

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


def chamfer_mask(
    length: float,
    *,
    edge: Literal["x", "y", "z"] = "z",
    size: float = 1.0,
    builder: ContractBuilder | None = None,
    feature_id: str = "chamfer",
) -> Part:
    """Create a chamfer wedge to subtract from edges.

    Returns a triangular prism that can be subtracted from a part to
    create a chamfer along an edge.  The wedge is positioned so that
    its apex sits at the corner and its base faces outward.

    Parameters
    ----------
    length : float
        Chamfer length along the edge axis (mm).
    edge : str
        Which axis the chamfer runs along: ``"x"``, ``"y"``, or ``"z"``.
    size : float
        Chamfer size — the distance from corner to base along each
        adjacent face (mm).  For a 1mm chamfer on a 90° corner, both
        faces lose 1mm.
    builder : ContractBuilder | None
        If provided, registers feature and checks.
    feature_id : str
        Base ID for entries.

    Returns
    -------
    Part
        The chamfer wedge solid (subtract from your part).
    """
    if edge not in ("x", "y", "z"):
        raise ValueError(f"edge must be 'x', 'y', or 'z', got '{edge}'")

    # Right triangle in XY sketch plane, extrude along Z.
    with BuildPart(mode=Mode.PRIVATE) as bp:
        with BuildSketch():
            Polygon([(0, 0), (size, 0), (0, size)])
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
                "description": f"chamfer_mask size={size}mm edge={edge} length={length}mm",
            },
            checks=[],
        )

    return result