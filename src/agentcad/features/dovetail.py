"""Dovetail helper: interlocking dovetail joint (male/female)."""
from __future__ import annotations

import math

from typing import TYPE_CHECKING, Literal

from build123d import (
    BuildPart,
    BuildSketch,
    Location,
    Mode,
    Part,
    Plane,
    Polygon,
    Rot,
    extrude,
)

if TYPE_CHECKING:
    from .contract import ContractBuilder

Gender = Literal["male", "female"]


def _make_profile(width: float, height: float, slope: float, clearance: float = 0.0) -> list[tuple[float, float]]:
    """Build the dovetail cross-section polygon in (Z, X) order for XZ plane."""
    # In XZ plane sketch: x → 3D-Z, y → 3D-X
    # Trapezoid: wider base at Z=0, narrower top at Z=height
    base_half = width / 2 + height / slope + clearance
    top_half = width / 2 + clearance
    return [
        (0, -base_half),
        (height, -top_half),
        (height, top_half),
        (0, base_half),
    ]


def dovetail(
    gender: Gender,
    width: float,
    height: float,
    slide: float,
    *,
    slope: float = 6.0,
    angle: float | None = None,
    taper: float = 0.0,
    center: tuple[float, float] = (0.0, 0.0),
    base_z: float = 0.0,
    builder: ContractBuilder | None = None,
    feature_id: str = "dovetail",
) -> Part:
    """Create a dovetail joint (male additive or female subtractive mask).

    Parameters
    ----------
    gender : str
        ``"male"`` returns a positive dovetail solid; ``"female"``
        returns a subtractive mask for the matching socket.
    width : float
        Width at the wider (top) end of the dovetail (mm).
    height : float
        How far the dovetail projects from its base (mm).
    slide : float
        Sliding distance / length along Y (mm).
    slope : float
        Rise/run ratio of the dovetail flanks. Default 6.
    angle : float or None
        Flank angle in degrees (overrides slope).
    taper : float
        Taper angle in degrees along the slide direction. 0 = straight.
    center : tuple[float, float]
        XY center position.
    base_z : float
        Z position of the base.
    builder : ContractBuilder | None
        If provided, registers feature and checks.
    feature_id : str
        Base ID for entries.

    Returns
    -------
    Part
        Male: positive dovetail solid. Female: subtractive mask.
    """
    if gender not in ("male", "female"):
        raise ValueError(f"gender must be 'male' or 'female', got '{gender}'")

    if angle is not None:
        slope = 1.0 / math.tan(math.radians(angle))

    cx, cy = center
    clearance = 0.1 if gender == "female" else 0.0

    profile = _make_profile(width, height, slope, clearance)

    # Build cross-section in XZ plane, extrude along Y
    plane = Plane(origin=(cx, cy, base_z), z_dir=(0, 1, 0))

    with BuildPart(mode=Mode.PRIVATE) as bp:
        with BuildSketch(plane):
            Polygon([(p[0], p[1]) for p in profile])
        extrude(amount=slide)

    result = bp.part

    if builder is not None:
        checks = [
            {
                "id": f"{feature_id}_bbox",
                "type": "bbox_size",
                "expected": [width + 2 * height / slope + 2 * clearance, slide, height],
                "tolerance": 1.0,
                "feature_ref": feature_id,
            },
        ]
        builder.add(
            feature={
                "id": feature_id,
                "description": f"dovetail {gender} w={width} h={height} slide={slide} slope={slope}",
            },
            checks=checks,
        )

    return result