"""Hardware dimension tables extracted from ISO/DIN standards.

Data sourced from NopSCADlib (GPL-3.0) empirically verified dimensions.
"""
from __future__ import annotations

from .screws import Screw, SCREWS, screw
from .nuts import Nut, NUTS, nut
from .washers import Washer, WASHERS, washer
from .inserts import Insert, INSERTS, insert

__all__ = [
    "Screw", "SCREWS", "screw",
    "Nut", "NUTS", "nut",
    "Washer", "WASHERS", "washer",
    "Insert", "INSERTS", "insert",
]
