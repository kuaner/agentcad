"""Rect tube helper: rectangular hollow tube."""
from __future__ import annotations

from typing import TYPE_CHECKING

from build123d import (
    Align,
    Box,
    BuildPart,
    Location,
    Mode,
    Part,
)

if TYPE_CHECKING:
    from .contract import ContractBuilder


def rect_tube(
    size: tuple[float, float, float],
    wall: float,
    *,
    center: tuple[float, float] = (0.0, 0.0),
    base_z: float = 0.0,
    builder: ContractBuilder | None = None,
    feature_id: str = "rect_tube",
) -> Part:
    """Create a rectangular hollow tube (box with inner cavity).

    Parameters
    ----------
    size : tuple
        (width, depth, height) of the outer rectangular tube (mm).
    wall : float
        Wall thickness on each side (mm). Inner cavity is reduced by
        2*wall in width and depth, and is open top/bottom.
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
        The rectangular hollow tube.
    """
    if len(size) != 3:
        raise ValueError(f"size must be (width, depth, height), got {size}")

    width, depth, height = size
    inner_w = width - 2 * wall
    inner_d = depth - 2 * wall

    cx, cy = center

    with BuildPart(mode=Mode.PRIVATE) as bp:
        Box(width, depth, height, align=(Align.CENTER, Align.CENTER, Align.MIN))
        if inner_w > 0 and inner_d > 0:
            Box(
                inner_w, inner_d, height + 1,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT,
            ).moved(Location((0, 0, -0.5)))

    result = bp.part.moved(Location((cx, cy, base_z)))

    if builder is not None:
        builder.add(
            feature={
                "id": feature_id,
                "description": f"rect_tube {width}x{depth}x{height}mm wall={wall}mm",
            },
            checks=[
                {
                    "id": f"{feature_id}_bbox",
                    "type": "bbox_size",
                    "expected": [width, depth, height],
                    "tolerance": 0.5,
                    "feature_ref": feature_id,
                },
                {
                    "id": f"{feature_id}_id",
                    "type": "inner_diameter_at_z",
                    "z": base_z + height / 2,
                    "expected": inner_w,
                    "tolerance": 0.5,
                    "center": [cx, cy],
                    "feature_ref": feature_id,
                },
            ],
        )

    return result