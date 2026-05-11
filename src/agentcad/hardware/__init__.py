"""Hardware dimension tables from ISO/DIN metric fastener standards.

Dimensions are derived from published ISO/DIN specifications (ISO 4014,
ISO 4032, DIN 934, DIN 125, etc.) — these are factual standard data, not
copyrightable expression. Values were cross-referenced against NopSCADlib
for accuracy verification only.
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
