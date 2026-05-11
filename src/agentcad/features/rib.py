"""Rib helper: reinforcing rib with auto-emitting wall thickness check."""
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


def rib(
    length: float,
    height: float,
    thickness: float,
    *,
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0),
    direction: str = "x",
    builder: ContractBuilder | None = None,
    feature_id: str = "rib",
) -> Part:
    """Create a reinforcing rib (thin wall).

    Parameters
    ----------
    length : float
        Rib length along the direction axis (mm).
    height : float
        Rib height in Z (mm).
    thickness : float
        Rib thickness (mm).
    origin : tuple[float, float, float]
        Origin point of the rib.
    direction : str
        Length axis: ``"x"`` or ``"y"``.
    builder : ContractBuilder | None
        If provided, registers feature and wall thickness check.
    feature_id : str
        Base ID for entries.

    Returns
    -------
    Part
        The rib solid.
    """
    if direction == "x":
        w, d = length, thickness
    elif direction == "y":
        w, d = thickness, length
    else:
        raise ValueError(f"direction must be 'x' or 'y', got {direction!r}")

    with BuildPart(mode=Mode.PRIVATE) as bp:
        Box(w, d, height, align=(Align.CENTER, Align.CENTER, Align.MIN))
    result = bp.part.moved(Location(origin))

    if builder is not None:
        checks: list[dict] = [
            {
                "id": f"{feature_id}_thickness",
                "type": "min_wall_thickness",
                "z": origin[2] + height / 2,
                "center": list(origin[:2]),
                "expected_min": thickness,
                "tolerance": 0.3,
                "feature_ref": feature_id,
            },
        ]
        builder.add(
            feature={
                "id": feature_id,
                "description": f"rib {length}x{thickness}x{height}mm along {direction}",
            },
            checks=checks,
        )

    return result
