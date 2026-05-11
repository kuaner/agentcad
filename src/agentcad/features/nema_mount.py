"""NEMA mount helper: stepper motor mounting hole pattern."""
from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from build123d import (
    Align,
    BuildPart,
    Cylinder,
    Location,
    Mode,
    Part,
)

from .mounting_pattern import MountingHoles  # noqa: F401 — kept for future integration

if TYPE_CHECKING:
    from .contract import ContractBuilder

NemaSize = Literal[8, 11, 14, 17, 23]

_NEMA_TABLE: dict[NemaSize, dict[str, float]] = {
    8:  {"frame": 20.3, "bore": 16.0, "screw_d": 2.0,  "spacing": 15.40, "shaft": 4.0},
    11: {"frame": 28.2, "bore": 22.0, "screw_d": 2.6,  "spacing": 23.11, "shaft": 5.0},
    14: {"frame": 35.2, "bore": 22.0, "screw_d": 3.0,  "spacing": 26.00, "shaft": 5.0},
    17: {"frame": 42.3, "bore": 22.0, "screw_d": 3.0,  "spacing": 31.00, "shaft": 5.0},
    23: {"frame": 57.0, "bore": 38.1, "screw_d": 5.1,  "spacing": 47.00, "shaft": 6.35},
}


def nema_mount(
    size: NemaSize = 17,
    depth: float = 5.0,
    *,
    center: tuple[float, float] = (0.0, 0.0),
    base_z: float = 0.0,
    builder: ContractBuilder | None = None,
    feature_id: str = "nema_mount",
) -> Part:
    """Create a NEMA stepper motor mounting hole pattern.

    Returns a subtractive Part with a center bore and 4 corner
    mounting holes matching the NEMA standard pattern.

    Parameters
    ----------
    size : int
        NEMA motor size: 8, 11, 14, 17, or 23.
    depth : float
        Hole depth in mm.
    center : tuple[float, float]
        XY center position (motor center).
    base_z : float
        Z position of the hole entry face.
    builder : ContractBuilder or None
        If provided, registers feature and checks.
    feature_id : str
        Base ID for entries.

    Returns
    -------
    Part
        The subtractive hole pattern.
    """
    if size not in _NEMA_TABLE:
        raise ValueError(f"size must be one of {list(_NEMA_TABLE.keys())}, got {size}")

    specs = _NEMA_TABLE[size]
    bore_d = specs["bore"]
    screw_d = specs["screw_d"]
    spacing = specs["spacing"]

    cx, cy = center
    overshoot = 1.0

    with BuildPart(mode=Mode.PRIVATE) as bp:
        # Center bore
        Cylinder(
            radius=bore_d / 2,
            height=depth + overshoot,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
            mode=Mode.ADD,
        ).moved(Location((cx, cy, base_z - overshoot / 2)))

        # 4 corner mounting holes
        for dx, dy in [(spacing / 2, spacing / 2), (-spacing / 2, spacing / 2),
                        (spacing / 2, -spacing / 2), (-spacing / 2, -spacing / 2)]:
            Cylinder(
                radius=screw_d / 2,
                height=depth + overshoot,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.ADD,
            ).moved(Location((cx + dx, cy + dy, base_z - overshoot / 2)))

    result = bp.part

    if builder is not None:
        builder.add(
            feature={
                "id": feature_id,
                "description": f"NEMA{size} mount bore={bore_d}mm screw_d={screw_d}mm spacing={spacing}mm",
            },
            checks=[
                {
                    "id": f"{feature_id}_bore",
                    "type": "inner_diameter_at_z",
                    "z": base_z + depth / 2,
                    "center": [cx, cy],
                    "expected": bore_d,
                    "tolerance": 0.5,
                    "feature_ref": feature_id,
                },
                {
                    "id": f"{feature_id}_screw",
                    "type": "inner_diameter_at_z",
                    "z": base_z + depth / 2,
                    "center": [cx + spacing / 2, cy + spacing / 2],
                    "expected": screw_d,
                    "tolerance": 0.5,
                    "feature_ref": feature_id,
                },
            ],
        )

    return result