"""Slot helper: rectangular channel with auto-emitting section checks."""
from __future__ import annotations

from typing import TYPE_CHECKING

from build123d import (
    Align,
    BuildPart,
    Box,
    Location,
    Mode,
    Part,
)

if TYPE_CHECKING:
    from .contract import ContractBuilder


def slot(
    width: float,
    depth: float,
    height: float,
    *,
    center: tuple[float, float] = (0.0, 0.0),
    base_z: float = 0.0,
    direction: str = "x",
    builder: ContractBuilder | None = None,
    feature_id: str = "slot",
) -> Part:
    """Create a rectangular slot (negative solid to subtract).

    Parameters
    ----------
    width : float
        Slot width across the opening (mm).
    depth : float
        Slot depth (how deep it cuts) (mm).
    height : float
        Slot length along the direction axis (mm).
    center : tuple[float, float]
        XY center position.
    base_z : float
        Z position of the slot base.
    direction : str
        Length axis: ``"x"`` or ``"y"``.
    builder : ContractBuilder | None
        If provided, registers feature and section checks.
    feature_id : str
        Base ID for entries.

    Returns
    -------
    Part
        Negative solid (slot channel) to subtract from parent.
    """
    if direction == "x":
        w, d = height, width
    elif direction == "y":
        w, d = width, height
    else:
        raise ValueError(f"direction must be 'x' or 'y', got {direction!r}")

    with BuildPart(mode=Mode.PRIVATE) as bp:
        Box(w, d, depth, align=(Align.CENTER, Align.CENTER, Align.MIN))
    result = bp.part.moved(Location((center[0], center[1], base_z)))

    if builder is not None:
        half_w = w / 2 * 0.8
        half_d = d / 2 * 0.8
        checks: list[dict] = [
            {
                "id": f"{feature_id}_section",
                "type": "section_bbox_at_z",
                "z": base_z + depth / 2,
                "region": [
                    [center[0] - half_w, center[1] - half_d],
                    [center[0] + half_w, center[1] + half_d],
                ],
                "expected": "void",
                "tolerance": 0.3,
                "feature_ref": feature_id,
            },
        ]
        builder.add(
            feature={
                "id": feature_id,
                "description": f"slot {width}x{depth}x{height}mm along {direction}",
            },
            checks=checks,
        )

    return result
