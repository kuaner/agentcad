"""Heat-set and threaded insert dimension tables.

Dimensions from NopSCADlib (GPL-3.0, Chris Palmer). Hole diameters are
empirically verified for 3D printing — too loose and inserts pull out,
too tight and the plastic cracks.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

InsertKind = Literal["heat_set", "threaded"]


@dataclass(frozen=True)
class Insert:
    name: str
    screw_diameter: float
    outer_diameter: float
    length: float
    hole_diameter: float  # recommended hole for 3D printing
    kind: InsertKind = "heat_set"

    @property
    def wall_thickness(self) -> float:
        return (self.outer_diameter - self.screw_diameter) / 2


INSERTS: dict[str, Insert] = {}

_INSERT_DEFS: list[tuple[str, float, float, float, float, InsertKind]] = [
    # name, screw_dia, outer_dia, length, hole_dia, kind
    # Heat-set inserts (brass, ultrasonic)
    ("F1BM2", 2.0, 3.6, 4.0, 3.2, "heat_set"),
    ("F1BM2.5", 2.5, 4.6, 5.8, 4.0, "heat_set"),
    ("F1BM3", 3.0, 4.6, 5.8, 4.0, "heat_set"),
    ("F1BM4", 4.0, 6.3, 8.2, 5.6, "heat_set"),
    ("CNCKM2.5", 2.5, 4.6, 4.0, 4.0, "heat_set"),
    ("CNCKM3", 3.0, 4.6, 3.0, 4.0, "heat_set"),
    ("CNCKM4", 4.0, 6.3, 4.0, 5.6, "heat_set"),
    ("CNCKM5", 5.0, 7.1, 5.8, 6.4, "heat_set"),
    # Threaded inserts (DIN 7965)
    ("M3x8", 3.0, 6.0, 8.0, 5.0, "threaded"),
    ("M4x10", 4.0, 8.0, 10.0, 6.5, "threaded"),
    ("M5x12", 5.0, 10.0, 12.0, 8.5, "threaded"),
    ("M6x15", 6.0, 12.0, 15.0, 10.5, "threaded"),
    ("M8x18", 8.0, 16.0, 18.0, 14.5, "threaded"),
]


def _build_inserts() -> None:
    for name, sd, od, length, hd, kind in _INSERT_DEFS:
        INSERTS[name] = Insert(name=name, screw_diameter=sd, outer_diameter=od, length=length, hole_diameter=hd, kind=kind)


_build_inserts()


def insert(spec: str) -> Insert:
    """Look up an insert by name like 'F1BM3', 'CNCKM4', or 'M5x12'."""
    if spec in INSERTS:
        return INSERTS[spec]
    raise KeyError(f"unknown insert spec {spec!r}; available: {sorted(INSERTS)}")
