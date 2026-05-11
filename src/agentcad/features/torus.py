"""Torus helper: donut ring shape."""
from __future__ import annotations

import math

from typing import TYPE_CHECKING

from build123d import (
    BuildPart,
    BuildSketch,
    Circle,
    Location,
    Mode,
    Part,
    Plane,
    loft,
)

if TYPE_CHECKING:
    from .contract import ContractBuilder


def torus(
    major_radius: float,
    minor_radius: float,
    *,
    center: tuple[float, float] = (0.0, 0.0),
    base_z: float = 0.0,
    builder: ContractBuilder | None = None,
    feature_id: str = "torus",
) -> Part:
    """Create a torus (donut ring) shape.

    The torus is built by lofting between circular cross-sections
    placed around the major radius ring path.

    Parameters
    ----------
    major_radius : float
        Distance from the center of the torus to the center of the
        tube (mm). This is the ring radius.
    minor_radius : float
        Radius of the tube cross-section (mm). This is the tube thickness.
    center : tuple[float, float]
        XY center position.
    base_z : float
        Z position of the center (torus is centered vertically at this Z).
    builder : ContractBuilder or None
        If provided, registers feature and checks.
    feature_id : str
        Base ID for entries.

    Returns
    -------
    Part
        The torus ring.
    """
    if major_radius <= 0:
        raise ValueError(f"major_radius must be > 0, got {major_radius}")
    if minor_radius <= 0:
        raise ValueError(f"minor_radius must be > 0, got {minor_radius}")

    cx, cy = center
    n_sections = 24

    with BuildPart(mode=Mode.PRIVATE) as bp:
        for i in range(n_sections):
            angle = 360 * i / n_sections
            x = major_radius * math.cos(math.radians(angle))
            y = major_radius * math.sin(math.radians(angle))
            tangent_z = (
                -math.sin(math.radians(angle)),
                math.cos(math.radians(angle)),
                0,
            )
            with BuildSketch(Plane(origin=(x, y, 0), z_dir=tangent_z)):
                Circle(minor_radius)
        loft()

    result = bp.part.moved(Location((cx, cy, base_z)))

    if builder is not None:
        builder.add(
            feature={
                "id": feature_id,
                "description": f"torus major_r={major_radius} minor_r={minor_radius}",
            },
            checks=[
                {
                    "id": f"{feature_id}_od",
                    "type": "outer_diameter_at_z",
                    "z": base_z,
                    "expected": (major_radius + minor_radius) * 2,
                    "tolerance": minor_radius * 0.5,
                    "center": [cx, cy],
                    "feature_ref": feature_id,
                },
                {
                    "id": f"{feature_id}_id",
                    "type": "inner_diameter_at_z",
                    "z": base_z,
                    "expected": (major_radius - minor_radius) * 2,
                    "tolerance": minor_radius * 0.5,
                    "center": [cx, cy],
                    "feature_ref": feature_id,
                },
            ],
        )

    return result