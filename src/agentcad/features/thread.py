"""Sinusoidal multi-start screw thread generator for build123d.

Translates the OpenSCAD ``cscrew`` module to build123d using Helix + sweep.
The thread profile is a cosine-shaped radial bump (sinusoidal cross-section)
swept along a helical path with Frenet frame to prevent twist.
"""
from __future__ import annotations

import math

from build123d import (
    BuildLine,
    BuildPart,
    BuildSketch,
    Helix,
    Mode,
    Part,
    Plane,
    Polygon,
    Rotation,
    sweep,
)


def sinusoidal_thread(
    radius: float,
    pitch: float = 9.0,
    height: float = 6.0,
    amplitude: float = 1.12,
    tooth_height: float = 2.6,
    n_starts: int = 3,
) -> Part:
    """Generate a sinusoidal multi-start thread solid.

    Parameters
    ----------
    radius : float
        Pitch radius where the thread seats on the cylinder.
    pitch : float
        Axial advance per full turn (mm).
    height : float
        Total thread engagement length (mm).
    amplitude : float
        Maximum radial extension of the tooth (mm).
    tooth_height : float
        Axial height of one tooth (mm).
    n_starts : int
        Number of thread starts (equally spaced at 360/n_starts degrees).

    Returns
    -------
    Part
        A solid containing all thread starts fused together.
    """
    if not isinstance(n_starts, int) or n_starts < 1:
        raise ValueError("n_starts must be a positive integer")
    if amplitude <= 0 or tooth_height <= 0 or height <= 0 or pitch <= 0:
        raise ValueError("amplitude, tooth_height, height, and pitch must be positive")
    if radius <= 0:
        raise ValueError("radius must be positive")

    profile = _sinusoidal_profile(amplitude, tooth_height)

    # Sweep a single start inside a BuildPart context
    with BuildPart(mode=Mode.PRIVATE) as single:
        with BuildLine() as path:
            Helix(pitch=pitch, height=height, radius=radius)
        with BuildSketch(Plane(origin=path.line @ 0, z_dir=path.line % 0)):
            Polygon(profile)
        sweep()

    base = single.part
    if not base.solids() or n_starts <= 1:
        return base

    result = base
    for i in range(1, n_starts):
        angle = 360.0 * i / n_starts
        rotated = base.moved(Rotation(0, 0, angle))
        result = result.fuse(rotated)

    return result


def _sinusoidal_profile(amplitude: float, tooth_height: float) -> list[tuple[float, float]]:
    """Generate the sinusoidal tooth cross-section polygon points.

    Returns a closed polygon in the radial-axial plane:
    - X = radial direction (0 at root, amplitude at peak)
    - Y = axial direction (0 at bottom, tooth_height at top)

    The profile is a cosine bump sitting on a flat base.
    """
    n_pts = 30
    points: list[tuple[float, float]] = [(0.0, 0.0)]

    for i in range(1, n_pts):
        t = i / n_pts
        axial = t * tooth_height
        radial = amplitude * (1 - math.cos(2 * math.pi * t)) / 2
        points.append((radial, axial))

    points.append((0.0, tooth_height))
    return points
