"""Prismoid helper: tapered box with different top/bottom dimensions."""
from __future__ import annotations

from typing import TYPE_CHECKING

from build123d import (
    BuildPart,
    BuildSketch,
    Location,
    loft,
    Mode,
    Part,
    Plane,
    Rectangle,
)

if TYPE_CHECKING:
    from .contract import ContractBuilder


def prismoid(
    size_bottom: tuple[float, float],
    size_top: tuple[float, float],
    height: float,
    *,
    center: tuple[float, float] = (0.0, 0.0),
    base_z: float = 0.0,
    rounding: float = 0.0,
    builder: ContractBuilder | None = None,
    feature_id: str = "prismoid",
) -> Part:
    """Create a tapered box (prismoid) with different top/bottom dimensions.

    Parameters
    ----------
    size_bottom : tuple[float, float]
        (width, depth) of the bottom face (mm).
    size_top : tuple[float, float]
        (width, depth) of the top face (mm).
    height : float
        Prism height (mm).
    center : tuple[float, float]
        XY center position.
    base_z : float
        Z position of the base.
    rounding : float
        Optional edge rounding radius.
    builder : ContractBuilder | None
        If provided, registers feature and checks.
    feature_id : str
        Base ID for entries.

    Returns
    -------
    Part
        The tapered box.
    """
    cx, cy = center
    bw, bd = size_bottom
    tw, td = size_top

    with BuildPart(mode=Mode.PRIVATE) as bp:
        with BuildSketch(Plane(origin=(cx, cy, base_z))):
            Rectangle(bw, bd)
        with BuildSketch(Plane(origin=(cx, cy, base_z + height))):
            Rectangle(tw, td)
        loft()

    if rounding > 0:
        from build123d import fillet
        vertical_edges = [
            e for e in bp.edges()
            if abs(e @ (0, 0, 1)) > 0.9
        ]
        if vertical_edges:
            fillet(vertical_edges, radius=rounding)

    result = bp.part

    if builder is not None:
        checks = [
            {
                "id": f"{feature_id}_bbox",
                "type": "bbox_size",
                "expected": [
                    max(bw, tw),
                    max(bd, td),
                    height,
                ],
                "tolerance": 1.0,
                "feature_ref": feature_id,
            },
        ]
        builder.add(
            feature={
                "id": feature_id,
                "description": (
                    f"prismoid bottom={bw}x{bd} top={tw}x{td} h={height}mm"
                ),
            },
            checks=checks,
        )

    return result
