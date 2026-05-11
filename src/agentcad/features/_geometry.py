"""Shared geometry helpers for feature modules."""
import math


def hexagon_vertices(radius: float, n_sides: int = 6, rotation: float = 30.0) -> list[tuple[float, float]]:
    """Regular polygon vertices for a given circumradius.

    Parameters
    ----------
    radius : float
        Circumradius (distance from center to vertex).
    n_sides : int
        Number of polygon sides. Default 6 (hexagon).
    rotation : float
        Starting angle offset in degrees. Default 30 (flat-top hexagon).
    """
    return [
        (radius * math.cos(math.radians(360 / n_sides * i + rotation)),
         radius * math.sin(math.radians(360 / n_sides * i + rotation)))
        for i in range(n_sides)
    ]