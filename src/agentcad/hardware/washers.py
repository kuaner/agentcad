"""ISO metric washer dimension tables.

Dimensions from NopSCADlib (GPL-3.0, Chris Palmer).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

WasherKind = Literal["standard", "penny", "spring", "star", "rubber"]


@dataclass(frozen=True)
class Washer:
    name: str
    screw_diameter: float
    outer_diameter: float
    thickness: float
    kind: WasherKind = "standard"

    @property
    def outer_radius(self) -> float:
        return self.outer_diameter / 2

    @property
    def inner_diameter(self) -> float:
        return self.screw_diameter


WASHERS: dict[str, Washer] = {}

_WASHER_DEFS: list[tuple[str, float, float, float, WasherKind]] = [
    # name, screw_dia, outer_dia, thickness, kind
    ("M2", 2.0, 5.0, 0.3, "standard"),
    ("M2.5", 2.5, 5.9, 0.5, "standard"),
    ("M3", 3.0, 7.0, 0.5, "standard"),
    ("M3.5", 3.5, 8.0, 0.5, "standard"),
    ("M4", 4.0, 9.0, 0.8, "standard"),
    ("M5", 5.0, 10.0, 1.0, "standard"),
    ("M6", 6.0, 12.5, 1.5, "standard"),
    ("M8", 8.0, 17.0, 1.6, "standard"),
    # Penny washers (larger outer diameter)
    ("M3_penny", 3.0, 12.0, 0.8, "penny"),
    ("M4_penny", 4.0, 14.0, 0.8, "penny"),
    ("M5_penny", 5.0, 20.0, 1.4, "penny"),
    ("M6_penny", 6.0, 26.0, 1.5, "penny"),
    ("M8_penny", 8.0, 30.0, 1.5, "penny"),
    # Spring washers
    ("M3_spring", 3.0, 5.6, 1.0, "spring"),
    ("M4_spring", 4.0, 7.0, 1.2, "spring"),
    ("M5_spring", 5.0, 8.8, 1.6, "spring"),
    ("M6_spring", 6.0, 9.9, 1.9, "spring"),
    ("M8_spring", 8.0, 12.7, 2.0, "spring"),
    # Rubber washers
    ("M3_rubber", 3.0, 10.0, 1.5, "rubber"),
]


def _build_washers() -> None:
    for name, sd, od, t, kind in _WASHER_DEFS:
        WASHERS[name] = Washer(name=name, screw_diameter=sd, outer_diameter=od, thickness=t, kind=kind)


_build_washers()


def washer(spec: str) -> Washer:
    """Look up a washer by name like 'M3', 'M4_penny', or 'M3_spring'."""
    if spec in WASHERS:
        return WASHERS[spec]
    raise KeyError(f"unknown washer spec {spec!r}; available: {sorted(WASHERS)}")
