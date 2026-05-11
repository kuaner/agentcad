"""Shared involute gear math for spur_gear and ring_gear."""
import math


def involute_point(base_r: float, angle_deg: float) -> tuple[float, float]:
    """Point on the involute of a circle at the given unwinding angle."""
    a = angle_deg * math.pi / 180
    x = base_r * (math.cos(a) + a * math.sin(a))
    y = base_r * (math.sin(a) - a * math.cos(a))
    return (x, y)


def involute_polar(base_r: float, angle_deg: float) -> tuple[float, float]:
    """Involute point in polar coordinates (radius, angle from start)."""
    x, y = involute_point(base_r, angle_deg)
    r = math.sqrt(x * x + y * y)
    theta = math.atan2(y, x)
    return (r, theta)


def angle_at_radius(base_r: float, target_r: float) -> float:
    """Unwinding angle where the involute reaches the target radius."""
    a = 0.0
    r = base_r
    while r < target_r:
        a += 1.0
        x, y = involute_point(base_r, a)
        r = math.sqrt(x * x + y * y)
    # Refine with bisection
    lo, hi = a - 1.0, a
    for _ in range(20):
        mid = (lo + hi) / 2
        x, y = involute_point(base_r, mid)
        r = math.sqrt(x * x + y * y)
        if r < target_r:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2