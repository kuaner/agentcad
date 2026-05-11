"""Ring gear helper: internal involute gear (complement to spur_gear)."""
from __future__ import annotations

import math

from typing import TYPE_CHECKING

from build123d import (
    Align,
    BuildPart,
    BuildSketch,
    Circle,
    Cylinder,
    Location,
    Mode,
    Part,
    Polygon,
    extrude,
)

if TYPE_CHECKING:
    from .contract import ContractBuilder


def _involute_point(base_r: float, angle_deg: float) -> tuple[float, float]:
    """Point on the involute of a circle at the given unwinding angle."""
    a = angle_deg * math.pi / 180
    x = base_r * (math.cos(a) + a * math.sin(a))
    y = base_r * (math.sin(a) - a * math.cos(a))
    return (x, y)


def _involute_polar(base_r: float, angle_deg: float) -> tuple[float, float]:
    """Involute point in polar coordinates (radius, angle from start)."""
    x, y = _involute_point(base_r, angle_deg)
    r = math.sqrt(x * x + y * y)
    theta = math.atan2(y, x)
    return (r, theta)


def _angle_at_radius(base_r: float, target_r: float) -> float:
    """Unwinding angle where the involute reaches the target radius."""
    a = 0.0
    r = base_r
    while r < target_r:
        a += 1.0
        x, y = _involute_point(base_r, a)
        r = math.sqrt(x * x + y * y)
    lo, hi = a - 1.0, a
    for _ in range(20):
        mid = (lo + hi) / 2
        x, y = _involute_point(base_r, mid)
        r = math.sqrt(x * x + y * y)
        if r < target_r:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _ring_gear_profile_points(
    teeth: int,
    module: float,
    pressure_angle: float = 20.0,
    clearance: float = 0.25,
) -> list[tuple[float, float]]:
    """Generate ring gear tooth protrusion profile points.

    Each tooth protrudes inward from root circle (r_root) toward tip
    circle (r_tip). Returns points tracing all teeth as one closed polygon.
    """
    r_p = module * teeth / 2
    r_b = r_p * math.cos(math.radians(pressure_angle))
    r_root = r_p + (1 + clearance) * module
    r_tip = r_p - module

    n_involute_pts = 8

    # Involute angles at key radii
    ang_at_root = _angle_at_radius(r_b, r_root) if r_root > r_b else 0.0
    ang_at_tip = _angle_at_radius(r_b, r_tip) if r_tip > r_b else 0.0

    _, theta_at_root = _involute_polar(r_b, ang_at_root) if r_root > r_b else (r_root, 0.0)
    _, theta_at_tip = _involute_polar(r_b, ang_at_tip) if r_tip > r_b else (r_tip, 0.0)

    # For internal gear: tooth angular span
    # At pitch circle, tooth thickness = pi*module/2 (wider than spur)
    pitch_half_angle = (math.pi / teeth) / 2  # half tooth at pitch circle

    all_points: list[tuple[float, float]] = []

    for tooth_idx in range(teeth):
        rot = 2 * math.pi * tooth_idx / teeth
        center_angle = rot

        # Left flank: from root to tip
        left_root_angle = center_angle - pitch_half_angle * r_root / r_p
        left_tip_angle = center_angle - pitch_half_angle * r_tip / r_p

        # Right flank: from tip to root
        right_tip_angle = center_angle + pitch_half_angle * r_tip / r_p
        right_root_angle = center_angle + pitch_half_angle * r_root / r_p

        # Previous gap end angle (right root of previous tooth)
        prev_gap_end = center_angle - pitch_half_angle * r_root / r_p
        # The gap (space between teeth) at root circle
        gap_left = center_angle - (2 * math.pi / teeth) + pitch_half_angle * r_root / r_p
        gap_right = left_root_angle

        # Gap arc at root radius (space between teeth)
        for i in range(3):
            frac = i / 2
            a = gap_left + (gap_right - gap_left) * frac
            all_points.append((r_root * math.cos(a), r_root * math.sin(a)))

        # Left involute flank: root to tip (inward)
        for i in range(n_involute_pts + 1):
            frac = i / n_involute_pts
            r = r_root - (r_root - r_tip) * frac
            a = left_root_angle + (left_tip_angle - left_root_angle) * frac
            all_points.append((r * math.cos(a), r * math.sin(a)))

        # Tip arc (innermost)
        for i in range(3):
            frac = i / 2
            a = left_tip_angle + (right_tip_angle - left_tip_angle) * frac
            all_points.append((r_tip * math.cos(a), r_tip * math.sin(a)))

        # Right involute flank: tip to root (outward)
        for i in range(n_involute_pts + 1):
            frac = i / n_involute_pts
            r = r_tip + (r_root - r_tip) * frac
            a = right_tip_angle + (right_root_angle - right_tip_angle) * frac
            all_points.append((r * math.cos(a), r * math.sin(a)))

    return all_points


def ring_gear(
    teeth: int,
    module: float,
    thickness: float,
    rim_width: float | None = None,
    *,
    pressure_angle: float = 20.0,
    clearance: float = 0.25,
    backlash: float = 0.0,
    center: tuple[float, float] = (0.0, 0.0),
    base_z: float = 0.0,
    builder: ContractBuilder | None = None,
    feature_id: str = "ring_gear",
) -> Part:
    """Create an internal (ring) involute gear.

    Teeth protrude inward from the root circle toward the tip circle.
    The outer rim is a solid annulus between root circle and outer radius.

    Parameters
    ----------
    teeth : int
        Number of gear teeth.
    module : float
        Pitch diameter / teeth (mm).
    thickness : float
        Gear face width (mm).
    rim_width : float or None
        Outer rim width beyond root circle (mm). Default = module * 3.
    pressure_angle : float
        Involute pressure angle in degrees. Default 20.
    clearance : float
        Root clearance factor. Default 0.25.
    backlash : float
        Tooth thickness reduction (mm). Default 0.
    center : tuple[float, float]
        XY center position.
    base_z : float
        Z position of the base.
    builder : ContractBuilder or None
        If provided, registers feature and checks.
    feature_id : str
        Base ID for entries.

    Returns
    -------
    Part
        The internal ring gear.
    """
    if teeth < 6:
        raise ValueError(f"teeth must be >= 6, got {teeth}")
    if module <= 0:
        raise ValueError(f"module must be > 0, got {module}")
    if thickness <= 0:
        raise ValueError(f"thickness must be > 0, got {thickness}")

    if rim_width is None:
        rim_width = module * 3

    r_p = module * teeth / 2
    r_root = r_p + (1 + clearance) * module
    r_tip = r_p - module
    r_outer = r_root + rim_width

    cx, cy = center

    # Build: solid outer disk, subtract inner bore, add tooth protrusions
    overshoot = 1.0

    # Outer solid disk
    with BuildPart(mode=Mode.PRIVATE) as bp:
        with BuildSketch():
            Circle(r_outer)
        extrude(amount=thickness)

        # Subtract central bore at tip radius (removes all internal area)
        Cylinder(
            radius=r_tip,
            height=thickness + overshoot,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
            mode=Mode.SUBTRACT,
        ).moved(Location((0, 0, -overshoot / 2)))

    ring = bp.part

    # Build tooth protrusions (from r_tip outward to r_root)
    tooth_points = _ring_gear_profile_points(teeth, module, pressure_angle, clearance)

    with BuildPart(mode=Mode.PRIVATE) as tooth_bp:
        with BuildSketch():
            Polygon(tooth_points)
        extrude(amount=thickness)

    tooth_protrusions = tooth_bp.part

    result = ring.fuse(tooth_protrusions).moved(Location((cx, cy, base_z)))

    if builder is not None:
        builder.add(
            feature={
                "id": feature_id,
                "description": f"ring_gear teeth={teeth} module={module} thickness={thickness} rim={rim_width}",
            },
            checks=[
                {
                    "id": f"{feature_id}_od",
                    "type": "outer_diameter_at_z",
                    "z": base_z + thickness / 2,
                    "center": [cx, cy],
                    "expected": r_outer * 2,
                    "tolerance": module,
                    "feature_ref": feature_id,
                },
                {
                    "id": f"{feature_id}_id",
                    "type": "inner_diameter_at_z",
                    "z": base_z + thickness / 2,
                    "center": [cx, cy],
                    "expected": r_tip * 2,
                    "tolerance": module,
                    "feature_ref": feature_id,
                },
            ],
        )

    return result