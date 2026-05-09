"""Pure-geometry primitives for shape clearance and accessibility checks.

These helpers operate on declarative shape descriptors (no STL required),
so they can be reused both for static design-time prechecks and STL-based
validate-time spot checks.

Shape descriptors are dicts of the following forms:

  Box (axis-aligned):
    {"type": "box",
     "x_range": [x_min, x_max],
     "y_range": [y_min, y_max],
     "z_range": [z_min, z_max]}

  Cylinder along Z:
    {"type": "cylinder", "axis": "z",
     "center": [cx, cy],
     "radius": r,
     "z_range": [z_min, z_max]}

  Cylinder along X / Y (axis = "x" | "y"):
    {"type": "cylinder", "axis": "x",
     "center": [cy, cz],
     "radius": r,
     "x_range": [x_min, x_max]}

  Sphere:
    {"type": "sphere", "center": [cx, cy, cz], "radius": r}

All shapes are axis-aligned. Rotated shapes are intentionally out of scope
for this layer — design-time predicates should be expressible as AABB +
axis-aligned cylinder, which covers the vast majority of clearance and
interference checks for plate / bracket / shell parts.
"""
from __future__ import annotations

import math
from typing import Any

Vec3 = tuple[float, float, float]
Range = tuple[float, float]


# ---------------------------------------------------------------------------
# Shape introspection
# ---------------------------------------------------------------------------

def shape_aabb(shape: dict) -> dict:
    """Compute the 3D axis-aligned bounding box of a shape descriptor.

    Returns ``{"min": [x,y,z], "max": [x,y,z]}``.
    Raises ValueError on unsupported shape types.
    """
    kind = shape.get("type")
    if kind == "box":
        x0, x1 = sorted(_pair(shape["x_range"]))
        y0, y1 = sorted(_pair(shape["y_range"]))
        z0, z1 = sorted(_pair(shape["z_range"]))
        return {"min": [x0, y0, z0], "max": [x1, y1, z1]}
    if kind == "cylinder":
        axis = str(shape.get("axis", "z")).lower()
        r = float(shape["radius"])
        if axis == "z":
            cx, cy = _pair(shape["center"])
            z0, z1 = sorted(_pair(shape["z_range"]))
            return {"min": [cx - r, cy - r, z0], "max": [cx + r, cy + r, z1]}
        if axis == "x":
            cy, cz = _pair(shape["center"])
            x0, x1 = sorted(_pair(shape["x_range"]))
            return {"min": [x0, cy - r, cz - r], "max": [x1, cy + r, cz + r]}
        if axis == "y":
            cx, cz = _pair(shape["center"])
            y0, y1 = sorted(_pair(shape["y_range"]))
            return {"min": [cx - r, y0, cz - r], "max": [cx + r, y1, cz + r]}
        raise ValueError(f"unsupported cylinder axis: {axis!r}")
    if kind == "sphere":
        cx, cy, cz = _triple(shape["center"])
        r = float(shape["radius"])
        return {"min": [cx - r, cy - r, cz - r], "max": [cx + r, cy + r, cz + r]}
    raise ValueError(f"unsupported shape type: {kind!r}")


def aabb_axis_overlap(a: dict, b: dict, axis: int) -> float:
    """Return signed overlap of two AABBs along an axis (0/1/2 = x/y/z).

    Positive value: length of the overlapping interval.
    Zero / negative: separation (distance between projections, negated).
    """
    a_min, a_max = a["min"][axis], a["max"][axis]
    b_min, b_max = b["min"][axis], b["max"][axis]
    return min(a_max, b_max) - max(a_min, b_min)


# ---------------------------------------------------------------------------
# 2D distance helpers (XY plane)
# ---------------------------------------------------------------------------

def _pair(values) -> tuple[float, float]:
    a, b = values
    return float(a), float(b)


def _triple(values) -> tuple[float, float, float]:
    a, b, c = values
    return float(a), float(b), float(c)


def _xy_projection(shape: dict) -> dict:
    """Project a 3D shape onto the XY plane.

    Returns one of:
      {"kind": "rect", "x_range": (..), "y_range": (..)}
      {"kind": "circle", "center": (cx, cy), "radius": r}
      {"kind": "rect+circle_caps", ...}  # cylinder along x or y, simplified to bbox
    """
    aabb = shape_aabb(shape)
    kind = shape.get("type")
    if kind == "cylinder" and str(shape.get("axis", "z")).lower() == "z":
        cx, cy = _pair(shape["center"])
        return {"kind": "circle", "center": (cx, cy), "radius": float(shape["radius"])}
    return {
        "kind": "rect",
        "x_range": (aabb["min"][0], aabb["max"][0]),
        "y_range": (aabb["min"][1], aabb["max"][1]),
    }


def _point_to_rect_distance(px: float, py: float, x_range: Range, y_range: Range) -> float:
    """Shortest distance from a point to an axis-aligned rectangle.

    Returns 0 if the point is inside the rectangle.
    """
    x0, x1 = x_range
    y0, y1 = y_range
    dx = max(x0 - px, 0.0, px - x1)
    dy = max(y0 - py, 0.0, py - y1)
    return math.hypot(dx, dy)


def _rect_rect_distance(a: dict, b: dict) -> float:
    """Shortest distance between two axis-aligned rectangles.

    Returns 0 if they overlap.
    """
    ax0, ax1 = a["x_range"]
    ay0, ay1 = a["y_range"]
    bx0, bx1 = b["x_range"]
    by0, by1 = b["y_range"]
    dx = max(0.0, max(ax0 - bx1, bx0 - ax1))
    dy = max(0.0, max(ay0 - by1, by0 - ay1))
    return math.hypot(dx, dy)


def xy_clearance(shape_a: dict, shape_b: dict) -> dict:
    """Compute XY-projected clearance between two shapes.

    Returns {"clearance_mm": float, "kinds": [a_kind, b_kind]}.
    Negative clearance means the projections overlap (interference).
    """
    pa = _xy_projection(shape_a)
    pb = _xy_projection(shape_b)
    if pa["kind"] == "rect" and pb["kind"] == "rect":
        clearance = _rect_rect_distance(pa, pb)
        if clearance == 0.0 and _rects_overlap(pa, pb):
            clearance = -_rect_rect_overlap_depth(pa, pb)
    elif pa["kind"] == "circle" and pb["kind"] == "circle":
        cax, cay = pa["center"]
        cbx, cby = pb["center"]
        center_dist = math.hypot(cbx - cax, cby - cay)
        clearance = center_dist - pa["radius"] - pb["radius"]
    elif pa["kind"] == "circle" and pb["kind"] == "rect":
        cx, cy = pa["center"]
        center_to_rect = _point_to_rect_distance(cx, cy, pb["x_range"], pb["y_range"])
        clearance = center_to_rect - pa["radius"]
    elif pa["kind"] == "rect" and pb["kind"] == "circle":
        cx, cy = pb["center"]
        center_to_rect = _point_to_rect_distance(cx, cy, pa["x_range"], pa["y_range"])
        clearance = center_to_rect - pb["radius"]
    else:
        raise ValueError(f"unsupported projection kinds: {pa['kind']}, {pb['kind']}")
    return {"clearance_mm": clearance, "kinds": [pa["kind"], pb["kind"]]}


def _rects_overlap(a: dict, b: dict) -> bool:
    ax0, ax1 = a["x_range"]
    ay0, ay1 = a["y_range"]
    bx0, bx1 = b["x_range"]
    by0, by1 = b["y_range"]
    return not (ax1 < bx0 or bx1 < ax0 or ay1 < by0 or by1 < ay0)


def _rect_rect_overlap_depth(a: dict, b: dict) -> float:
    ax0, ax1 = a["x_range"]
    ay0, ay1 = a["y_range"]
    bx0, bx1 = b["x_range"]
    by0, by1 = b["y_range"]
    ox = min(ax1, bx1) - max(ax0, bx0)
    oy = min(ay1, by1) - max(ay0, by0)
    return min(ox, oy)


# ---------------------------------------------------------------------------
# 3D clearance — combines XY projection with Z overlap
# ---------------------------------------------------------------------------

def min_clearance_3d(shape_a: dict, shape_b: dict) -> dict:
    """Compute combined 3D clearance.

    Two shapes only physically interfere when:
      - they overlap in Z (their z_ranges intersect), AND
      - their XY projections also overlap.

    If shapes do not overlap in Z, ``z_separation_mm`` is positive and they
    cannot interfere regardless of XY layout. If they do overlap in Z, the
    XY-projected clearance is used.

    Returns {
      "clearance_mm": float,        # Negative if interfering, 0 if touching
      "z_overlap_mm": float,        # Negative if Z-separated
      "xy_clearance_mm": float,     # XY-projected only
      "interferes": bool,           # True iff clearance < 0
    }
    """
    aabb_a = shape_aabb(shape_a)
    aabb_b = shape_aabb(shape_b)
    z_overlap = aabb_axis_overlap(aabb_a, aabb_b, axis=2)
    xy = xy_clearance(shape_a, shape_b)
    xy_clearance_mm = float(xy["clearance_mm"])

    if z_overlap < 0:
        clearance = -z_overlap
        interferes = False
    elif abs(z_overlap) <= 1e-9:
        clearance = 0.0
        interferes = False
    else:
        clearance = xy_clearance_mm
        interferes = xy_clearance_mm < 0
    return {
        "clearance_mm": clearance,
        "z_overlap_mm": z_overlap,
        "xy_clearance_mm": xy_clearance_mm,
        "interferes": interferes,
    }


# ---------------------------------------------------------------------------
# STL-side helpers (operate on triangle list)
# ---------------------------------------------------------------------------

def slab_section_points(
    triangles: list,
    axis: int,
    pos: float,
) -> list[tuple[float, float]]:
    """Intersect mesh with an axis-aligned plane, return 2D points on the plane.

    For axis=2 (Z), returns (x, y) points; axis=0 returns (y, z); axis=1 returns (x, z).
    """
    points: list[tuple[float, float]] = []
    other_a, other_b = [i for i in (0, 1, 2) if i != axis]
    for tri in triangles:
        a, b, c = tri
        edges = ((a, b), (b, c), (c, a))
        for p, q in edges:
            pa = p[axis] - pos
            qa = q[axis] - pos
            if abs(pa) < 1e-8 and abs(qa) < 1e-8:
                points.append((p[other_a], p[other_b]))
                points.append((q[other_a], q[other_b]))
            elif pa == 0:
                points.append((p[other_a], p[other_b]))
            elif qa == 0:
                points.append((q[other_a], q[other_b]))
            elif (pa < 0 < qa) or (qa < 0 < pa):
                t = (pos - p[axis]) / (q[axis] - p[axis])
                u = p[other_a] + t * (q[other_a] - p[other_a])
                v = p[other_b] + t * (q[other_b] - p[other_b])
                points.append((u, v))
    return points


def hole_accessibility_at_axis(
    triangles: list,
    axis: int,
    pos: float,
    center: tuple[float, float],
    hole_radius: float,
    clearance_radius: float,
) -> dict:
    """Check whether a tool can reach a hole on an axis-aligned access plane.

    Imagines a tool envelope of radius ``clearance_radius`` centered at
    ``center`` on the section plane. Points on the mesh at this plane that fall
    within the annulus (hole_radius < r < clearance_radius) indicate that
    material is blocking tool access.

    For axis=Z, ``center`` is (x, y). For axis=Y, ``center`` is (x, z). For
    axis=X, ``center`` is (y, z). Use a plane in the approach corridor, not a
    plane buried inside the surrounding plate material.

    Returns {
      "ok": bool,                 # True = no obstruction within annulus
      "blocking_point_count": int,
      "min_blocking_radius": float | None,  # closest blocking material to hole edge
    }
    """
    cx, cy = center
    points = slab_section_points(triangles, axis=axis, pos=pos)
    blocking = []
    for x, y in points:
        r = math.hypot(x - cx, y - cy)
        if hole_radius + 1e-6 < r < clearance_radius - 1e-6:
            blocking.append(r)
    return {
        "ok": len(blocking) == 0,
        "blocking_point_count": len(blocking),
        "min_blocking_radius": min(blocking) if blocking else None,
    }


def hole_accessibility_at_z(
    triangles: list,
    z: float,
    center: tuple[float, float],
    hole_radius: float,
    clearance_radius: float,
) -> dict:
    """Backward-compatible Z-axis wrapper for hole access checks."""
    return hole_accessibility_at_axis(
        triangles, 2, z, center, hole_radius, clearance_radius
    )


def min_wall_thickness_at_z(
    triangles: list,
    z: float,
    region: tuple[tuple[float, float], tuple[float, float]] | None = None,
    sample_resolution: float = 0.5,
) -> dict:
    """Estimate the minimum wall thickness at a Z section by point-pair sweep.

    Computes the minimum distance between any two distinct points (after
    deduplication at ``sample_resolution``) of the mesh-plane intersection
    inside ``region``.

    IMPORTANT: ``region`` is essential — without it, the result is dominated
    by adjacent-edge points of the same wall (yielding the sample resolution).
    Restrict ``region`` to a corridor that crosses *two opposing walls* so the
    minimum pair distance approximates the wall-to-wall gap (e.g., the
    inner/outer wall spacing of a hollow shell, or the gap between two
    parallel features).

    Args:
      triangles: STL triangle list
      z: section height
      region: optional ((x0,y0),(x1,y1)) to restrict the analysis
      sample_resolution: minimum distance to count as a distinct sample (mm)

    Returns {
      "ok": bool,
      "point_count": int,
      "min_thickness_mm": float | None,
      "min_pair": [(x1,y1), (x2,y2)] | None,
    }
    """
    points = slab_section_points(triangles, axis=2, pos=z)
    if region is not None:
        (rx0, ry0), (rx1, ry1) = region
        points = [(x, y) for x, y in points if rx0 <= x <= rx1 and ry0 <= y <= ry1]
    if len(points) < 2:
        return {"ok": False, "point_count": len(points),
                "min_thickness_mm": None, "min_pair": None,
                "error": "need at least 2 intersection points"}

    # Deduplicate near-coincident points to avoid measuring noise distances.
    dedup: list[tuple[float, float]] = []
    for x, y in points:
        if not any(math.hypot(x - dx, y - dy) < sample_resolution for dx, dy in dedup):
            dedup.append((x, y))
    if len(dedup) < 2:
        return {"ok": False, "point_count": len(dedup),
                "min_thickness_mm": None, "min_pair": None,
                "error": "all points coincide after deduplication"}

    best = float("inf")
    best_pair: tuple[tuple[float, float], tuple[float, float]] | None = None
    for i, (x1, y1) in enumerate(dedup):
        for x2, y2 in dedup[i + 1:]:
            d = math.hypot(x2 - x1, y2 - y1)
            if d < best:
                best = d
                best_pair = ((x1, y1), (x2, y2))
    return {
        "ok": True,
        "point_count": len(dedup),
        "min_thickness_mm": best,
        "min_pair": [list(best_pair[0]), list(best_pair[1])] if best_pair else None,
    }


def is_point_inside_aabb(point: Vec3, aabb: dict, eps: float = 0.0) -> bool:
    px, py, pz = point
    return (aabb["min"][0] - eps <= px <= aabb["max"][0] + eps
            and aabb["min"][1] - eps <= py <= aabb["max"][1] + eps
            and aabb["min"][2] - eps <= pz <= aabb["max"][2] + eps)


def parse_shape(payload: Any) -> dict:
    """Validate a shape descriptor; raise ValueError on malformed input."""
    if not isinstance(payload, dict):
        raise ValueError("shape must be a JSON object")
    kind = payload.get("type")
    if kind == "box":
        for key in ("x_range", "y_range", "z_range"):
            if key not in payload:
                raise ValueError(f"box shape missing required field: {key}")
            _pair(payload[key])
        return payload
    if kind == "cylinder":
        axis = str(payload.get("axis", "z")).lower()
        if axis not in ("x", "y", "z"):
            raise ValueError(f"cylinder axis must be x|y|z, got {axis!r}")
        if "radius" not in payload or "center" not in payload:
            raise ValueError("cylinder shape requires 'center' and 'radius'")
        if axis == "z" and "z_range" not in payload:
            raise ValueError("z-axis cylinder requires 'z_range'")
        if axis == "x" and "x_range" not in payload:
            raise ValueError("x-axis cylinder requires 'x_range'")
        if axis == "y" and "y_range" not in payload:
            raise ValueError("y-axis cylinder requires 'y_range'")
        return payload
    if kind == "sphere":
        if "center" not in payload or "radius" not in payload:
            raise ValueError("sphere shape requires 'center' and 'radius'")
        _triple(payload["center"])
        return payload
    raise ValueError(f"unsupported shape type: {kind!r} (expected box|cylinder|sphere)")
