"""ISO metric screw dimension tables.

Dimensions from ISO 4762, ISO 7045, ISO 4014, ISO 10642, ISO 7380
published standards. Values cross-referenced with NopSCADlib for accuracy
verification. Tap and clearance radii are empirically verified for 3D printing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

HeadStyle = Literal["cap", "pan", "cs", "cs_cap", "hex", "grub", "dome"]


@dataclass(frozen=True)
class Screw:
    name: str
    nominal_diameter: float
    head_style: HeadStyle
    head_diameter: float
    head_height: float
    socket_depth: float
    socket_af: float  # across flats
    max_thread_length: float
    tap_radius: float  # hole radius for tapping
    clearance_radius: float  # hole radius for free fit

    @property
    def pitch(self) -> float:
        return COARSE_PITCH.get(self.nominal_diameter, 0.0)

    @property
    def head_radius(self) -> float:
        return self.head_diameter / 2

    def counterbore_diameter(self, clearance: float = 0.2) -> float:
        return self.head_diameter + clearance * 2

    def counterbore_depth(self, extra: float = 0.2) -> float:
        return self.head_height + extra

    def through_hole_diameter(self, fit: str = "normal") -> float:
        multipliers = {"tight": 1.0, "normal": 1.1, "loose": 1.2}
        return self.nominal_diameter * multipliers.get(fit, 1.1)


COARSE_PITCH: dict[float, float] = {
    1.4: 0.3, 1.6: 0.35, 1.7: 0.35,
    2.0: 0.4, 2.5: 0.45,
    3.0: 0.5, 3.5: 0.6,
    4.0: 0.7, 5.0: 0.8,
    6.0: 1.0, 8.0: 1.25,
    10.0: 1.5, 12.0: 1.75,
    14.0: 2.0, 16.0: 2.0,
}

SCREWS: dict[str, Screw] = {}

TAP_AND_CLEARANCE: dict[float, tuple[float, float]] = {
    2.0: (0.8, 1.2),
    2.5: (1.025, 1.4),
    3.0: (1.25, 1.65),
    3.5: (1.25, 1.75),
    4.0: (1.65, 2.2),
    5.0: (2.1, 2.65),
    6.0: (2.5, 3.2),
    8.0: (3.375, 4.2),
}

_SCREW_DEFS: list[tuple[str, HeadStyle, float, float, float, float, float, float]] = [
    # name, head_style, diameter, head_dia, head_h, socket_depth, socket_af, max_thread
    # Socket head cap screws (ISO 4762)
    ("M2_cap", "cap", 2.0, 3.8, 2.0, 1.0, 1.5, 16),
    ("M2.5_cap", "cap", 2.5, 4.5, 2.5, 1.1, 2.0, 17),
    ("M3_cap", "cap", 3.0, 5.5, 3.0, 1.3, 2.5, 18),
    ("M4_cap", "cap", 4.0, 7.0, 4.0, 2.0, 3.0, 20),
    ("M5_cap", "cap", 5.0, 8.5, 5.0, 2.5, 4.0, 22),
    ("M6_cap", "cap", 6.0, 10.0, 6.0, 3.3, 5.0, 24),
    ("M8_cap", "cap", 8.0, 13.0, 8.0, 4.3, 6.0, 28),
    # Countersunk socket head (ISO 10642)
    ("M2_cs_cap", "cs_cap", 2.0, 3.8, 0.0, 0.65, 1.3, 16),
    ("M3_cs_cap", "cs_cap", 3.0, 6.0, 0.0, 1.05, 2.0, 18),
    ("M4_cs_cap", "cs_cap", 4.0, 8.0, 0.0, 1.49, 2.5, 20),
    ("M5_cs_cap", "cs_cap", 5.0, 10.0, 0.0, 3.00, 3.0, 22),
    ("M6_cs_cap", "cs_cap", 6.0, 12.0, 0.0, 2.50, 4.0, 24),
    ("M8_cs_cap", "cs_cap", 8.0, 16.0, 0.0, 3.50, 5.0, 28),
    # Button/dome head (ISO 7380)
    ("M2_dome", "dome", 2.0, 3.5, 1.3, 0.6, 1.3, 16),
    ("M2.5_dome", "dome", 2.5, 5.35, 1.6, 0.8, 2.0, 17),
    ("M3_dome", "dome", 3.0, 5.7, 1.65, 1.04, 2.0, 18),
    ("M4_dome", "dome", 4.0, 7.6, 2.2, 1.3, 2.5, 20),
    ("M5_dome", "dome", 5.0, 9.5, 2.75, 1.56, 3.0, 22),
    ("M6_dome", "dome", 6.0, 10.5, 3.3, 2.5, 4.0, 24),
    ("M8_dome", "dome", 8.0, 14.0, 4.4, 3.0, 5.0, 30),
    # Pan head (ISO 7045)
    ("M2.5_pan", "pan", 2.5, 4.7, 1.7, 0.0, 0.0, 0),
    ("M3_pan", "pan", 3.0, 5.4, 2.0, 0.0, 0.0, 0),
    ("M4_pan", "pan", 4.0, 7.8, 3.3, 0.0, 0.0, 0),
    ("M5_pan", "pan", 5.0, 10.0, 3.95, 0.0, 0.0, 0),
    ("M6_pan", "pan", 6.0, 12.0, 4.75, 0.0, 0.0, 0),
    # Hex head (ISO 4014)
    ("M3_hex", "hex", 3.0, 6.4, 2.125, 0.0, 0.0, 0),
    ("M4_hex", "hex", 4.0, 8.1, 2.925, 0.0, 0.0, 0),
    ("M5_hex", "hex", 5.0, 9.2, 3.65, 0.0, 0.0, 0),
    ("M6_hex", "hex", 6.0, 11.5, 4.15, 0.0, 0.0, 0),
    ("M8_hex", "hex", 8.0, 15.0, 5.65, 0.0, 0.0, 22),
    # Grub / set screws (ISO 4026)
    ("M3_grub", "grub", 3.0, 0.0, 0.0, 2.5, 1.5, 0),
    ("M4_grub", "grub", 4.0, 0.0, 0.0, 2.4, 2.0, 0),
    ("M5_grub", "grub", 5.0, 0.0, 0.0, 2.4, 2.5, 0),
    ("M6_grub", "grub", 6.0, 0.0, 0.0, 2.4, 3.0, 0),
    # Countersunk flat head (ISO 7046)
    ("M3_cs", "cs", 3.0, 6.0, 0.0, 0.0, 0.0, 18),
    ("M4_cs", "cs", 4.0, 8.0, 0.0, 0.0, 0.0, 20),
    ("M5_cs", "cs", 5.0, 10.0, 0.0, 0.0, 0.0, 22),
]


def _build_screws() -> None:
    for name, style, dia, hd, hh, sd, saf, mtl in _SCREW_DEFS:
        tap, clear = TAP_AND_CLEARANCE.get(dia, (dia * 0.85 / 2, dia * 1.1 / 2))
        SCREWS[name] = Screw(
            name=name,
            nominal_diameter=dia,
            head_style=style,
            head_diameter=hd,
            head_height=hh,
            socket_depth=sd,
            socket_af=saf,
            max_thread_length=mtl,
            tap_radius=tap,
            clearance_radius=clear,
        )


_build_screws()


def screw(spec: str) -> Screw:
    """Look up a screw by name like 'M3_cap' or 'M4_hex'.

    Shorthand without head style defaults to cap: 'M3' → 'M3_cap'.
    """
    if spec in SCREWS:
        return SCREWS[spec]
    cap_name = f"{spec}_cap"
    if cap_name in SCREWS:
        return SCREWS[cap_name]
    raise KeyError(f"unknown screw spec {spec!r}; available: {sorted(SCREWS)}")
