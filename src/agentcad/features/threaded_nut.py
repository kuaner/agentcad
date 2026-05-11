"""Threaded nut helper: hex nut with internal thread profile."""
from __future__ import annotations

from typing import TYPE_CHECKING

from build123d import (
    Align,
    BuildPart,
    BuildSketch,
    Cylinder,
    Location,
    Mode,
    Part,
    Polygon,
    extrude,
)

from ..hardware.nuts import Nut, nut as nut_lookup
from ..hardware.screws import COARSE_PITCH
from ._geometry import hexagon_vertices
from .thread import sinusoidal_thread

if TYPE_CHECKING:
    from .contract import ContractBuilder


def threaded_nut(
    spec: str | Nut = "M3",
    *,
    center: tuple[float, float] = (0.0, 0.0),
    base_z: float = 0.0,
    builder: ContractBuilder | None = None,
    feature_id: str = "threaded_nut",
) -> Part:
    """Create a hex nut with internal sinusoidal thread.

    Returns a positive solid with hex outer profile and helical
    thread peaks protruding from the bore wall. The bore has
    sinusoidal thread ridges running along its length.

    Parameters
    ----------
    spec : str or Nut
        Nut specification like "M3", "M4". Uses hardware dimensions.
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
        The threaded hex nut solid.
    """
    n = nut_lookup(spec) if isinstance(spec, str) else spec
    corner_r = n.width_across_corners / 2
    thickness = n.thickness
    bore_d = n.screw_diameter
    bore_r = bore_d / 2

    pitch = COARSE_PITCH.get(bore_d, 0.0)
    if pitch == 0.0:
        raise ValueError(f"no coarse pitch for diameter {bore_d}mm; specify a standard M-size")

    cx, cy = center
    hex_verts = hexagon_vertices(corner_r)

    # Hex body with smooth bore hole
    with BuildPart(mode=Mode.PRIVATE) as bp:
        with BuildSketch():
            Polygon(hex_verts)
        extrude(amount=thickness)

        Cylinder(
            radius=bore_r,
            height=thickness + 1,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
            mode=Mode.SUBTRACT,
        ).moved(Location((0, 0, -0.5)))

    nut_part = bp.part

    # Build thread ring separately and subtract the inner bore
    # to get just the thread ridges (peaks that protrude from bore wall)
    thread_ring = sinusoidal_thread(
        radius=bore_r,
        pitch=pitch,
        height=thickness,
    )

    # Subtract the bore cylinder from the thread to isolate just the ridges
    with BuildPart(mode=Mode.PRIVATE) as thread_bp:
        Cylinder(
            radius=bore_r - pitch / 4,
            height=thickness + 1,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
            mode=Mode.ADD,
        ).moved(Location((0, 0, -0.5)))

    bore_core = thread_bp.part
    ridges = thread_ring.cut(bore_core)

    result = nut_part.fuse(ridges).moved(Location((cx, cy, base_z)))

    if builder is not None:
        builder.add(
            feature={
                "id": feature_id,
                "description": f"threaded_nut {n.name} bore={bore_d}mm pitch={pitch}mm h={thickness}mm",
            },
            checks=[
                {
                    "id": f"{feature_id}_bore",
                    "type": "inner_diameter_at_z",
                    "z": base_z + thickness / 2,
                    "center": [cx, cy],
                    "expected": bore_d,
                    "tolerance": 0.5,
                    "feature_ref": feature_id,
                },
            ],
        )

    return result