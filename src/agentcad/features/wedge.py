"""Wedge helper: triangular solid (gusset, support, angled bracket)."""
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


def wedge(
    width: float,
    depth: float,
    height: float,
    *,
    direction: Literal["+x", "-x", "+y", "-y"] = "+x",
    builder: ContractBuilder | None = None,
    feature_id: str = "wedge",
) -> Part:
    """Create a triangular prism (wedge/gusset).

    The right-triangle cross-section has *depth* along one axis and
    *height* along Z.  *width* is the extrusion length.  ``direction``
    determines which axis *width* runs along.

    * ``"+x"`` — width along X, depth along Y, height along Z
    * ``"-x"`` — same shape, offset so it fills −X
    * ``"+y"`` — width along Y, depth along X, height along Z
    * ``"-y"`` — same shape, offset so it fills −Y

    Parameters
    ----------
    width : float
        Extrusion width (mm).
    depth : float
        Base depth of the triangular cross-section (mm).
    height : float
        Height of the triangular cross-section along Z (mm).
    direction : str
        ``"+x"``, ``"-x"``, ``"+y"``, or ``"-y"``.
    builder : ContractBuilder | None
        If provided, registers feature and checks.
    feature_id : str
        Base ID for entries.

    Returns
    -------
    Part
        The triangular prism.
    """
    if direction not in ("+x", "-x", "+y", "-y"):
        raise ValueError(f"direction must be '+x', '-x', '+y', or '-y', got '{direction}'")

    # Build in default orientation: depth along sketch-X, height along sketch-Y,
    # extrude (width) along Z.  Result: X=depth, Y=height, Z=width.
    with BuildPart(mode=Mode.PRIVATE) as bp:
        with BuildSketch():
            Polygon([(0, 0), (depth, 0), (0, height)])
        extrude(amount=width)

    part = bp.part

    # Default part has X=depth, Y=height, Z=width.
    # Rotate to match direction.
    if direction == "+y":
        # +y: want width=Y, depth=X, height=Z → already matches (X=depth, Y=height, Z=width)
        # but we want width=Y, depth=X. Currently Y=height not depth.
        # Need: X=depth, Y=width, Z=height → Rot(Z=90) swaps X/Y → X=height, Y=depth, Z=width
        # Then Rot(X=90) swaps Y/Z → X=height, Y=width, Z=depth... no
        # Let me think: Rot(Z=90) → (X,Y) → (Y,-X) → new X=height, new Y=depth, Z=width
        # Hmm. We want X=depth, Y=width, Z=height.
        # Currently: X=depth, Y=height, Z=width
        # Rot(X=-90) → Y,Z → (Z,-Y) → X=depth, Y=width, Z=-height... almost!
        # Actually Rot(90,0,0) rotates around X: Y→Z, Z→-Y
        # After Rot(X=90): X=depth, Y=width, Z=-height (Z is inverted)
        # Need to also shift Z
        result = part.moved(Rot(90, 0, 0)).moved(Location((0, 0, height)))
    elif direction == "-y":
        result = part.moved(Rot(-90, 0, 0))
    elif direction == "+x":
        # +x: want width=X, depth=Y, height=Z
        # Currently: X=depth, Y=height, Z=width
        # Rot(Z=90) → X→Y, Y→-X → X=height, Y=depth, Z=width
        # Then Rot(Y=90) → Z→X, X→-Z → X=width, Y=depth, Z=-height
        result = part.moved(Rot(0, -90, 90)).moved(Location((0, 0, height)))
    elif direction == "-x":
        result = part.moved(Rot(0, 90, 90))

    if builder is not None:
        checks = [
            {
                "id": f"{feature_id}_bbox",
                "type": "bbox_size",
                "expected": [width, depth, height],
                "tolerance": 1.0,
                "feature_ref": feature_id,
            },
        ]
        builder.add(
            feature={
                "id": feature_id,
                "description": f"wedge {width}x{depth}x{height}mm dir={direction}",
            },
            checks=checks,
        )

    return result