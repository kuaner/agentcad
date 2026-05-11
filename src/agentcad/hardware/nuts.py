"""ISO metric nut dimension tables.

Dimensions from published ISO/DIN specifications. Values cross-referenced
with NopSCADlib for accuracy verification.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

NutStyle = Literal["hex", "thin_square", "wing", "t_nut", "hammer_nut", "weld"]


@dataclass(frozen=True)
class Nut:
    name: str
    screw_diameter: float
    width_across_corners: float  # max across-corners (hex width)
    thickness: float
    nyloc_thickness: float  # height with nylon insert
    trap_depth: float  # recommended nut trap depth for 3D printing
    style: NutStyle = "hex"

    @property
    def width_across_flats(self) -> float:
        import math
        return self.width_across_corners * math.cos(math.pi / 6)

    def pocket_diameter(self, clearance: float = 0.3) -> float:
        return self.width_across_corners + clearance * 2


NUTS: dict[str, Nut] = {}

_NUT_DEFS: list[tuple[str, float, float, float, float, float, NutStyle]] = [
    # name, screw_dia, across_corners, thickness, nyloc_h, trap_depth, style
    ("M2_nut", 2.0, 4.9, 1.6, 2.4, 1.75, "hex"),
    ("M2.5_nut", 2.5, 5.8, 2.2, 3.8, 2.5, "hex"),
    ("M3_nut", 3.0, 6.4, 2.4, 4.0, 3.0, "hex"),
    ("M4_nut", 4.0, 8.1, 3.2, 5.0, 4.0, "hex"),
    ("M5_nut", 5.0, 9.2, 4.0, 6.25, 4.0, "hex"),
    ("M6_nut", 6.0, 11.5, 5.0, 8.0, 5.0, "hex"),
    ("M6_half_nut", 6.0, 11.5, 3.0, 8.0, 3.0, "hex"),
    ("M8_nut", 8.0, 15.0, 6.5, 8.0, 6.5, "hex"),
    # DIN 562 thin square nuts
    ("M3_thin_square", 3.0, 5.5, 1.8, 0.0, 0.0, "thin_square"),
    ("M4_thin_square", 4.0, 7.0, 2.2, 0.0, 0.0, "thin_square"),
    ("M5_thin_square", 5.0, 8.0, 2.7, 0.0, 0.0, "thin_square"),
    ("M6_thin_square", 6.0, 10.0, 3.2, 0.0, 0.0, "thin_square"),
    ("M8_thin_square", 8.0, 13.0, 4.0, 0.0, 0.0, "thin_square"),
    # Wing nut
    ("M4_wing", 4.0, 10.0, 3.75, 0.0, 0.0, "wing"),
    # T-nuts for aluminum extrusion
    ("M3_t_nut", 3.0, 6.0, 3.0, 4.0, 0.0, "t_nut"),
    ("M4_t_nut", 4.0, 6.0, 3.7, 4.7, 0.0, "t_nut"),
    ("M5_t_nut", 5.0, 6.0, 3.7, 4.7, 0.0, "t_nut"),
    ("M6_t_nut", 6.0, 8.0, 6.6, 8.5, 0.0, "t_nut"),
    # Hammer nuts
    ("M3_hammer", 3.0, 6.0, 2.75, 4.0, 0.0, "hammer_nut"),
    ("M4_hammer", 4.0, 6.0, 3.25, 4.5, 0.0, "hammer_nut"),
]


def _build_nuts() -> None:
    for name, sd, ac, t, ny, td, style in _NUT_DEFS:
        NUTS[name] = Nut(
            name=name,
            screw_diameter=sd,
            width_across_corners=ac,
            thickness=t,
            nyloc_thickness=ny,
            trap_depth=td,
            style=style,
        )


_build_nuts()


def nut(spec: str) -> Nut:
    """Look up a nut by name like 'M3_nut' or 'M4_thin_square'.

    Shorthand defaults to hex: 'M3' → 'M3_nut'.
    """
    if spec in NUTS:
        return NUTS[spec]
    hex_name = f"{spec}_nut"
    if hex_name in NUTS:
        return NUTS[hex_name]
    raise KeyError(f"unknown nut spec {spec!r}; available: {sorted(NUTS)}")
