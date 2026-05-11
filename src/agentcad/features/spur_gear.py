"""Spur gear helper: involute spur/helical gear."""
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
    Plane,
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


def _involute_radius_at_angle(base_r: float, angle_deg: float) -> float:
    """Radius of the involute curve at a given unwinding angle."""
    x, y = _involute_point(base_r, angle_deg)
    return math.sqrt(x * x + y * y)


def _angle_at_radius(base_r: float, target_r: float) -> float:
    """Unwinding angle where the involute reaches the target radius."""
    a = 0.0
    while _involute_radius_at_angle(base_r, a) < target_r:
        a += 1.0
    # Refine with bisection
    lo, hi = a - 1.0, a
    for _ in range(20):
        mid = (lo + hi) / 2
        if _involute_radius_at_angle(base_r, mid) < target_r:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _involute_polar(base_r: float, angle_deg: float) -> tuple[float, float]:
    """Involute point in polar coordinates (radius, angle from start)."""
    x, y = _involute_point(base_r, angle_deg)
    r = math.sqrt(x * x + y * y)
    theta = math.atan2(y, x)
    return (r, theta)


def _gear_profile_points(
    teeth: int,
    module: float,
    pressure_angle: float = 20.0,
    clearance: float = 0.25,
    backlash: float = 0.0,
) -> list[tuple[float, float]]:
    """Generate the full gear outline as a list of (x, y) points.

    Uses the involute curve for tooth flanks, with root and tip arcs.
    """
    r_p = module * teeth / 2  # pitch radius
    r_b = r_p * math.cos(math.radians(pressure_angle))  # base radius
    r_o = r_p + module  # outer (tip) radius — addendum = module
    r_r = r_p - (1 + clearance) * module  # root radius — dedendum = (1+clearance)*module

    # Half tooth thickness at pitch circle (radians)
    pitch_tooth_angle = math.pi / teeth - backlash / (2 * r_p)

    # Involute angle at key radii
    ang_at_pitch = _angle_at_radius(r_b, r_p)
    ang_at_outer = _angle_at_radius(r_b, r_o)

    # Involute polar angles at pitch and outer
    _, theta_at_pitch = _involute_polar(r_b, ang_at_pitch)
    _, theta_at_outer = _involute_polar(r_b, ang_at_outer)

    # Tooth center offset: the involute starts at angle 0, but the tooth
    # centerline is at pitch_tooth_angle from the start of the left flank
    center_offset = pitch_tooth_angle / 2 + theta_at_pitch

    # Build points for one tooth
    tooth_points: list[tuple[float, float]] = []

    # Root arc from previous tooth gap to start of left flank
    root_start_angle = -(math.pi / teeth) + center_offset
    root_end_angle = center_offset - theta_at_pitch + theta_at_outer * 0  # simplified

    # Left involute flank: from root to outer
    left_start_angle = center_offset - theta_at_pitch
    num_involute_pts = 8
    for i in range(num_involute_pts + 1):
        frac = i / num_involute_pts
        # Map from root radius to outer radius
        r_target = r_r + (r_o - r_r) * frac
        if r_target < r_b:
            # Below base circle — use radial line from root to base
            angle = left_start_angle
            tooth_points.append((r_target * math.cos(angle), r_target * math.sin(angle)))
        else:
            a_inv = _angle_at_radius(r_b, r_target)
            _, theta_inv = _involute_polar(r_b, a_inv)
            angle = center_offset - theta_at_pitch + theta_inv
            tooth_points.append((r_target * math.cos(angle), r_target * math.sin(angle)))

    # Tip arc
    tip_left = center_offset - theta_at_pitch + theta_at_outer
    tip_right = center_offset + theta_at_pitch - theta_at_outer
    # Arc at outer radius from tip_left to tip_right
    if tip_left < tip_right:
        for i in range(3):
            frac = i / 2
            angle = tip_left + (tip_right - tip_left) * frac
            tooth_points.append((r_o * math.cos(angle), r_o * math.sin(angle)))

    # Right involute flank: from outer to root (mirror of left)
    for i in range(num_involute_pts, -1, -1):
        frac = i / num_involute_pts
        r_target = r_r + (r_o - r_r) * frac
        if r_target < r_b:
            angle = center_offset + theta_at_pitch
            tooth_points.append((r_target * math.cos(angle), r_target * math.sin(angle)))
        else:
            a_inv = _angle_at_radius(r_b, r_target)
            _, theta_inv = _involute_polar(r_b, a_inv)
            angle = center_offset + theta_at_pitch - theta_inv
            tooth_points.append((r_target * math.cos(angle), r_target * math.sin(angle)))

    # Root arc between teeth (gap)
    gap_start = center_offset + pitch_tooth_angle
    gap_end = center_offset + 2 * math.pi / teeth - pitch_tooth_angle
    # Simplified: arc at root radius
    for i in range(3):
        frac = i / 2
        angle = gap_start + (gap_end - gap_start) * frac
        tooth_points.append((r_r * math.cos(angle), r_r * math.sin(angle)))

    # Rotate-copy for all teeth
    all_points: list[tuple[float, float]] = []
    for tooth_idx in range(teeth):
        rot = 2 * math.pi * tooth_idx / teeth
        cos_r, sin_r = math.cos(rot), math.sin(rot)
        for px, py in tooth_points:
            all_points.append((px * cos_r - py * sin_r, px * sin_r + py * cos_r))

    return all_points


def spur_gear(
    teeth: int,
    module: float,
    thickness: float,
    *,
    shaft_diameter: float = 0.0,
    pressure_angle: float = 20.0,
    clearance: float = 0.25,
    backlash: float = 0.0,
    center: tuple[float, float] = (0.0, 0.0),
    base_z: float = 0.0,
    builder: ContractBuilder | None = None,
    feature_id: str = "spur_gear",
) -> Part:
    """Create an involute spur gear.

    Parameters
    ----------
    teeth : int
        Number of gear teeth.
    module : float
        Pitch diameter / teeth (mm). Standard ISO metric module.
    thickness : float
        Gear face width / thickness along the axis (mm).
    shaft_diameter : float
        Central shaft hole diameter (mm). 0 = solid (no shaft hole).
    pressure_angle : float
        Involute pressure angle in degrees. Default 20 (ISO standard).
    clearance : float
        Root clearance factor. Default 0.25 (25% of module).
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
        The spur gear.
    """
    if teeth < 6:
        raise ValueError(f"teeth must be >= 6, got {teeth}")
    if module <= 0:
        raise ValueError(f"module must be > 0, got {module}")
    if thickness <= 0:
        raise ValueError(f"thickness must be > 0, got {thickness}")

    r_p = module * teeth / 2
    r_o = r_p + module  # tip radius
    r_r = r_p - (1 + clearance) * module  # root radius

    cx, cy = center

    profile_points = _gear_profile_points(teeth, module, pressure_angle, clearance, backlash)

    with BuildPart(mode=Mode.PRIVATE) as bp:
        # Gear body from involute profile
        with BuildSketch():
            Polygon(profile_points)
        extrude(amount=thickness)

        # Shaft hole
        if shaft_diameter > 0:
            shaft_r = shaft_diameter / 2
            overshoot = 1.0
            Cylinder(
                radius=shaft_r,
                height=thickness + overshoot,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT,
            ).moved(Location((0, 0, -overshoot / 2)))

    result = bp.part.moved(Location((cx, cy, base_z)))

    if builder is not None:
        checks = [
            {
                "id": f"{feature_id}_bbox",
                "type": "bbox_size",
                "expected": [r_o * 2, r_o * 2, thickness],
                "tolerance": module,
                "feature_ref": feature_id,
            },
            {
                "id": f"{feature_id}_tip_od",
                "type": "outer_diameter_at_z",
                "z": thickness / 2,
                "expected": r_o * 2,
                "tolerance": module,
                "center": [cx, cy],
                "feature_ref": feature_id,
            },
        ]
        if shaft_diameter > 0:
            checks.append({
                "id": f"{feature_id}_shaft_id",
                "type": "inner_diameter_at_z",
                "z": thickness / 2,
                "expected": shaft_diameter,
                "tolerance": shaft_diameter * 0.1,
                "center": [cx, cy],
                "feature_ref": feature_id,
            })
        builder.add(
            feature={
                "id": feature_id,
                "description": f"spur_gear teeth={teeth} module={module} thickness={thickness}",
            },
            checks=checks,
        )

    return result