from __future__ import annotations

from ..stl import Triangle
from .types import AXIS_X, AXIS_Y, Segment2D

def section_segments(
    triangles: list[Triangle],
    axis: int,
    value: float,
) -> list[Segment2D]:
    """Extract 2D line segments where the mesh intersects an axis-aligned plane.

    ``axis``: 0=X (YZ plane), 1=Y (XZ plane), 2=Z (XY plane).

    Each triangle that straddles the plane contributes one line segment.
    Returns segments in the 2D coordinate system of the cut plane:
      - Z cut  → (X, Y)
      - X cut  → (Y, Z)
      - Y cut  → (X, Z)
    """
    segs: list[Segment2D] = []
    for tri in triangles:
        seg = _tri_seg(tri, axis, value)
        if seg is not None:
            segs.append(seg)
    return segs


def _tri_seg(tri: Triangle, axis: int, value: float) -> Segment2D | None:
    """Intersect one triangle with an axis-aligned plane."""
    verts = list(tri)
    pts: list[tuple[float, float]] = []

    for i in range(3):
        p = verts[i]
        q = verts[(i + 1) % 3]
        dp = p[axis] - value
        dq = q[axis] - value

        if abs(dp) < 1e-8 and abs(dq) < 1e-8:
            # Both vertices on the plane: add both (edge lies on section).
            _add_unique(pts, _proj(p, axis))
            _add_unique(pts, _proj(q, axis))
        elif abs(dp) < 1e-8:
            _add_unique(pts, _proj(p, axis))
        elif abs(dq) < 1e-8:
            pass  # q will be handled as p in the next iteration
        elif (dp < 0) != (dq < 0):
            t = dp / (dp - dq)
            ix = p[0] + t * (q[0] - p[0])
            iy = p[1] + t * (q[1] - p[1])
            iz = p[2] + t * (q[2] - p[2])
            _add_unique(pts, _proj((ix, iy, iz), axis))

        if len(pts) == 2:
            return (pts[0], pts[1])

    return None


def _proj(pt: tuple, axis: int) -> tuple[float, float]:
    """Drop the section axis to get a 2D point in the cut plane."""
    if axis == AXIS_X:
        return (pt[1], pt[2])   # (Y, Z)
    if axis == AXIS_Y:
        return (pt[0], pt[2])   # (X, Z)
    return (pt[0], pt[1])       # (X, Y)


def _add_unique(pts: list[tuple[float, float]], p: tuple[float, float]) -> None:
    if not any(abs(p[0] - q[0]) < 1e-6 and abs(p[1] - q[1]) < 1e-6 for q in pts):
        pts.append(p)
