"""Screw/bolt 3D visual geometry for assembly visualization."""
from __future__ import annotations

from typing import TYPE_CHECKING

from build123d import (
    Align,
    BuildPart,
    Cylinder,
    Location,
    Mode,
    Part,
)

from ..hardware.screws import Screw, screw as screw_lookup
from .thread import sinusoidal_thread

if TYPE_CHECKING:
    from .contract import ContractBuilder


def screw(
    spec: str | Screw = "M3",
    length: float = 12.0,
    *,
    center: tuple[float, float] = (0.0, 0.0),
    base_z: float = 0.0,
    builder: ContractBuilder | None = None,
    feature_id: str = "screw",
) -> Part:
    """Create a screw/bolt 3D visual geometry.

    Returns a positive Part with shaft, thread, and head matching
    the specified screw spec. Intended for assembly visualization,
    not subtractive use.

    Parameters
    ----------
    spec : str or Screw
        Screw specification (e.g. "M3", "M3_cap", "M5_pan").
    length : float
        Total shaft length in mm (head height not included).
    center : tuple[float, float]
        XY center position (screw axis).
    base_z : float
        Z position of the shaft base (threaded end).
    builder : ContractBuilder or None
        If provided, registers feature and checks.
    feature_id : str
        Base ID for entries.

    Returns
    -------
    Part
        The screw geometry (positive, for assembly visualization).
    """
    s = screw_lookup(spec) if isinstance(spec, str) else spec
    shaft_r = s.nominal_diameter / 2
    head_r = s.head_diameter / 2
    head_h = s.head_height
    pitch = s.pitch

    cx, cy = center
    shaft_base = base_z
    shaft_top = shaft_base + length
    head_base = shaft_top

    # Threaded shaft
    shaft = sinusoidal_thread(
        radius=shaft_r,
        pitch=pitch,
        height=length,
    ).moved(Location((cx, cy, shaft_base)))

    # Head cylinder
    with BuildPart(mode=Mode.PRIVATE) as bp:
        Cylinder(
            radius=head_r,
            height=head_h,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
            mode=Mode.ADD,
        ).moved(Location((cx, cy, head_base)))
    head = bp.part

    result = shaft.fuse(head)

    if builder is not None:
        builder.add(
            feature={
                "id": feature_id,
                "description": f"Screw {s.name} shaft={s.nominal_diameter}mm head={s.head_diameter}mm length={length}mm",
            },
            checks=[
                {
                    "id": f"{feature_id}_head",
                    "type": "outer_diameter_at_z",
                    "z": head_base + head_h / 2,
                    "center": [cx, cy],
                    "expected": s.head_diameter,
                    "tolerance": 1.0,
                    "feature_ref": feature_id,
                },
                {
                    "id": f"{feature_id}_shaft",
                    "type": "outer_diameter_at_z",
                    "z": shaft_base + length / 2,
                    "center": [cx, cy],
                    "expected": s.nominal_diameter,
                    "tolerance": 1.0,
                    "feature_ref": feature_id,
                },
            ],
        )

    return result