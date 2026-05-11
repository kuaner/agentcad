"""Snap pin helpers: double-ended snap-fit pin and matching socket."""
from __future__ import annotations

import math

from typing import TYPE_CHECKING, Literal

from build123d import (
    Align,
    Box,
    BuildPart,
    Cone,
    Cylinder,
    Location,
    Mode,
    Part,
    Rot,
    Sphere,
)

if TYPE_CHECKING:
    from .contract import ContractBuilder

PinSize = Literal["tiny", "small", "medium", "standard"]

_SIZE_TABLE: dict[PinSize, dict[str, float]] = {
    "tiny":     {"diameter": 2.5, "length": 4.0,  "snap": 0.25, "nub_depth": 0.9,  "thickness": 0.8},
    "small":    {"diameter": 3.2, "length": 6.0,  "snap": 0.4,  "nub_depth": 1.2,  "thickness": 1.0},
    "medium":   {"diameter": 4.6, "length": 8.0,  "snap": 0.45, "nub_depth": 1.5,  "thickness": 1.4},
    "standard": {"diameter": 7.0, "length": 10.8, "snap": 0.5,  "nub_depth": 1.8,  "thickness": 1.8},
}


def _resolve_size(
    size: PinSize,
    diameter: float | None,
    length: float | None,
    snap: float | None,
    nub_depth: float | None,
    thickness: float | None,
) -> dict[str, float]:
    defaults = _SIZE_TABLE[size]
    return {
        "diameter":  diameter  if diameter  is not None else defaults["diameter"],
        "length":    length    if length    is not None else defaults["length"],
        "snap":      snap      if snap      is not None else defaults["snap"],
        "nub_depth": nub_depth if nub_depth is not None else defaults["nub_depth"],
        "thickness": thickness if thickness is not None else defaults["thickness"],
    }


def snap_pin(
    size: PinSize = "standard",
    *,
    diameter: float | None = None,
    length: float | None = None,
    snap: float | None = None,
    nub_depth: float | None = None,
    thickness: float | None = None,
    clearance: float = 0.2,
    pointed: bool = True,
    center: tuple[float, float] = (0.0, 0.0),
    base_z: float = 0.0,
    builder: ContractBuilder | None = None,
    feature_id: str = "snap_pin",
) -> Part:
    """Create a double-ended snap-fit pin.

    Returns a positive solid Part with locking nubs at both ends.
    The pin is hollow inside (thin walls) to allow the nubs to flex.

    Parameters
    ----------
    size : str
        Predefined size: "tiny", "small", "medium", or "standard".
    diameter : float or None
        Override pin outer diameter (mm).
    length : float or None
        Override pin total length (mm).
    snap : float or None
        Override nub projection depth (mm).
    nub_depth : float or None
        Override nub distance from pin end (mm).
    thickness : float or None
        Override wall thickness (mm).
    clearance : float
        Shrink pin from socket walls (mm). Default 0.2.
    pointed : bool
        Pointed tip (True) or rounded tip (False).
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
        The snap-fit pin.
    """
    if size not in _SIZE_TABLE:
        raise ValueError(f"size must be one of {list(_SIZE_TABLE.keys())}, got '{size}'")

    params = _resolve_size(size, diameter, length, snap, nub_depth, thickness)
    d = params["diameter"]
    l = params["length"]
    s = params["snap"]
    nd = params["nub_depth"]
    t = params["thickness"]

    r = (d - clearance) / 2
    tip_h = r
    nub_r = r + s
    nub_h = s * 2
    inner_r = max(r - t, 0)

    cx, cy = center

    with BuildPart(mode=Mode.PRIVATE) as bp:
        # Shaft cylinder
        Cylinder(radius=r, height=l, align=(Align.CENTER, Align.CENTER, Align.MIN))

        # Nub rings at both ends
        for z_off in [nd, l - nd]:
            Cylinder(
                radius=nub_r,
                height=nub_h,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            ).moved(Location((0, 0, z_off - nub_h / 2)))

        # Tips
        if pointed:
            Cone(
                bottom_radius=r, top_radius=0, height=tip_h,
                align=(Align.CENTER, Align.CENTER, Align.MAX),
            )
            Cone(
                bottom_radius=r, top_radius=0, height=tip_h,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            ).moved(Location((0, 0, l)))
        else:
            Sphere(radius=r)
            Sphere(radius=r).moved(Location((0, 0, l)))

        # Hollow interior
        if inner_r > 0:
            Cylinder(
                radius=inner_r,
                height=l + 0.5,
                align=(Align.CENTER, Align.CENTER, Align.CENTER),
                mode=Mode.SUBTRACT,
            ).moved(Location((0, 0, l / 2)))

            # Flex slots near each nub (4 thin cross-slots)
            slot_w = inner_r * 1.6
            slot_h = nd + s + 0.5
            for z_center in [nd, l - nd]:
                for angle in [0, 90]:
                    Box(
                        slot_w, t * 0.4, slot_h,
                        align=(Align.CENTER, Align.CENTER, Align.CENTER),
                        mode=Mode.SUBTRACT,
                    ).moved(Rot(0, 0, angle)).moved(Location((0, 0, z_center)))

    result = bp.part.moved(Location((cx, cy, base_z)))

    if builder is not None:
        builder.add(
            feature={
                "id": feature_id,
                "description": f"snap_pin size={size} d={d} l={l} snap={s}",
            },
            checks=[
                {
                    "id": f"{feature_id}_bbox",
                    "type": "bbox_size",
                    "expected": [d + 2 * s, d + 2 * s, l + 2 * tip_h],
                    "tolerance": 1.0,
                    "feature_ref": feature_id,
                },
                {
                    "id": f"{feature_id}_shaft_od",
                    "type": "outer_diameter_at_z",
                    "z": l / 2,
                    "expected": d,
                    "tolerance": 0.5,
                    "center": [cx, cy],
                    "feature_ref": feature_id,
                },
            ],
        )

    return result


def snap_pin_socket(
    size: PinSize = "standard",
    *,
    diameter: float | None = None,
    length: float | None = None,
    snap: float | None = None,
    nub_depth: float | None = None,
    thickness: float | None = None,
    fixed: bool = True,
    clearance: float = 0.2,
    pointed: bool = True,
    center: tuple[float, float] = (0.0, 0.0),
    base_z: float = 0.0,
    builder: ContractBuilder | None = None,
    feature_id: str = "snap_pin_socket",
) -> Part:
    """Create a snap-fit socket (subtractive mask).

    Returns a subtractive Part for the matching socket cavity.
    ``fixed=True`` produces a flat-sided socket (anti-rotation);
    ``fixed=False`` produces a round socket.

    Parameters
    ----------
    size : str
        Predefined size matching snap_pin sizes.
    diameter : float or None
        Override socket diameter (mm).
    length : float or None
        Override socket length (mm).
    snap : float or None
        Override nub groove width (mm).
    nub_depth : float or None
        Override nub groove depth position (mm).
    thickness : float or None
        Override wall thickness (mm). Not used for socket but kept for size resolution.
    fixed : bool
        True = flat-sided socket (no rotation); False = round.
    clearance : float
        Socket wall clearance from pin (mm). Default 0.2.
    pointed : bool
        Match pin tip shape (pointed or rounded).
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
        The subtractive socket mask.
    """
    if size not in _SIZE_TABLE:
        raise ValueError(f"size must be one of {list(_SIZE_TABLE.keys())}, got '{size}'")

    params = _resolve_size(size, diameter, length, snap, nub_depth, thickness)
    d = params["diameter"]
    l = params["length"]
    s = params["snap"]
    nd = params["nub_depth"]

    r = d / 2 + clearance
    nub_r = r + s
    nub_h = s * 2
    tip_h = d / 2 if pointed else d / 2
    flat_w = d * math.sqrt(2) / 2 if fixed else nub_r + s

    cx, cy = center

    with BuildPart(mode=Mode.PRIVATE) as bp:
        # Main cylindrical cavity
        Cylinder(radius=r, height=l, align=(Align.CENTER, Align.CENTER, Align.MIN))

        # Nub grooves at both ends
        for z_off in [nd, l - nd]:
            Cylinder(
                radius=nub_r,
                height=nub_h,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            ).moved(Location((0, 0, z_off - nub_h / 2)))

        # Tip cavities at both ends
        if pointed:
            Cone(
                bottom_radius=r, top_radius=0, height=tip_h,
                align=(Align.CENTER, Align.CENTER, Align.MAX),
            )
            Cone(
                bottom_radius=r, top_radius=0, height=tip_h,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            ).moved(Location((0, 0, l)))
        else:
            Sphere(radius=r)
            Sphere(radius=r).moved(Location((0, 0, l)))

        # For fixed=True: clip sides to flat D-shape
        if fixed:
            total_h = l + 2 * tip_h + 1
            for sign in [-1, 1]:
                Box(
                    nub_r * 2 + s * 2 + 1, r * 2 - flat_w, total_h,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                    mode=Mode.SUBTRACT,
                ).moved(Location((0, sign * (flat_w / 2 + (r * 2 - flat_w) / 2), -0.5)))

    result = bp.part.moved(Location((cx, cy, base_z)))

    if builder is not None:
        socket_width = flat_w * 2 if fixed else (nub_r + s) * 2
        builder.add(
            feature={
                "id": feature_id,
                "description": f"snap_pin_socket size={size} d={d} l={l} fixed={fixed}",
            },
            checks=[
                {
                    "id": f"{feature_id}_bbox",
                    "type": "bbox_size",
                    "expected": [nub_r * 2, socket_width, l + 2 * tip_h],
                    "tolerance": 1.5,
                    "feature_ref": feature_id,
                },
                {
                    "id": f"{feature_id}_id",
                    "type": "inner_diameter_at_z",
                    "z": l / 2,
                    "expected": d,
                    "tolerance": 0.5,
                    "center": [cx, cy],
                    "feature_ref": feature_id,
                },
            ],
        )

    return result