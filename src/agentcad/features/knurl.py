"""Helical knurl pattern generator for build123d.

Translates the OpenSCAD ``knurl`` / ``apply_knurl`` modules to build123d.
Creates a subtractive solid of helical grooves that form a diamond or
straight knurl pattern when applied to a cylindrical surface.

Each groove is swept individually and returned as a list of Parts.
The caller subtracts them from the body one at a time for better performance
than fusing all grooves first.
"""
from __future__ import annotations

import math
from typing import Sequence

from build123d import (
    BuildLine,
    BuildPart,
    BuildSketch,
    Circle,
    Helix,
    Mode,
    Part,
    Plane,
    Polygon,
    Rotation,
    sweep,
)


def helical_knurl(
    radius: float,
    height: float,
    angle: float = 35.0,
    depth: float = 0.4,
    width: float = 1.5,
    density: float = 0.8,
    shape: int = 4,
    diamond: bool = True,
) -> Sequence[Part]:
    """Generate helical knurl groove parts for subtraction.

    Parameters
    ----------
    radius : float
        Cylinder surface radius where knurl grooves are cut.
    height : float
        Height of the knurl zone (mm).
    angle : float
        Helix angle in degrees (controls groove steepness).
    depth : float
        Radial depth of each groove (mm).
    width : float
        Circumferential width of each groove (mm).
    density : float
        Spacing factor 0-1 (higher = denser grooves).
    shape : int
        Number of sides for groove cross-section polygon (0 = circle).
    diamond : bool
        If True, create cross-hatch pattern (both helix directions).
        If False, single-direction grooves only.

    Returns
    -------
    list[Part]
        Individual groove solids, to be subtracted from the target body.
    """
    if depth <= 0 or width <= 0 or height <= 0 or radius <= 0:
        raise ValueError("all dimensions must be positive")

    angle_rad = math.radians(angle)
    n = max(1, round(2 * math.pi * radius / ((density + 1) * 2 * width) * math.cos(angle_rad)))
    pitch = 2 * math.pi * radius / math.tan(angle_rad)

    grooves: list[Part] = []

    # Right-hand grooves
    _build_groove_set(grooves, radius, height, pitch, n, depth, width, shape, lefthand=False)

    # Left-hand grooves (for diamond pattern)
    if diamond:
        _build_groove_set(grooves, radius, height, pitch, n, depth, width, shape, lefthand=True)

    return grooves


def _groove_profile(depth: float, width: float, shape: int):
    """Create the groove cross-section sketch in a BuildSketch context."""
    r = min(depth, width) / 2
    if shape == 0 or shape >= 20:
        Circle(radius=r)
    else:
        pts = []
        for i in range(shape):
            a = 2 * math.pi * i / shape + math.pi / 2
            pts.append((r * math.cos(a), r * math.sin(a)))
        Polygon(pts)


def _build_groove_set(
    grooves: list[Part],
    radius: float,
    height: float,
    pitch: float,
    n: int,
    depth: float,
    width: float,
    shape: int,
    lefthand: bool,
) -> None:
    """Build one groove then rotate-copy it n times."""
    try:
        with BuildPart(mode=Mode.PRIVATE) as single:
            with BuildLine() as path:
                Helix(pitch=pitch, height=height, radius=radius, lefthand=lefthand)
            with BuildSketch(Plane(origin=path.line @ 0, z_dir=path.line % 0)):
                _groove_profile(depth, width, shape)
            sweep()
    except (ValueError, RuntimeError):
        return

    base = single.part
    if not base.solids():
        return

    grooves.append(base)
    for i in range(1, n):
        angle = 360.0 * i / n
        if lefthand:
            angle += 180.0 / n
        grooves.append(base.moved(Rotation(0, 0, angle)))
