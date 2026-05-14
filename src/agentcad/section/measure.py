from __future__ import annotations

import math

from .analysis import analyze_section_segments, _bbox_payload
from .types import Segment2D, _AXIS_NAME, _PLANE_LABELS

def query_section_measurements(
    segments: list[Segment2D],
    axis: int,
    value: float,
    *,
    region: tuple[tuple[float, float], tuple[float, float]] | None = None,
    line_u: float | None = None,
    line_v: float | None = None,
    point: tuple[float, float] | None = None,
    precision: int = 4,
) -> dict:
    """Run optional ad-hoc measurements against an extracted section."""
    measurements: dict = {}
    if region is not None:
        measurements["region"] = measure_section_region(segments, axis, value, region, precision=precision)
    if line_u is not None:
        measurements["line_u"] = measure_section_line(segments, axis, value, "u", line_u, precision=precision)
    if line_v is not None:
        measurements["line_v"] = measure_section_line(segments, axis, value, "v", line_v, precision=precision)
    if point is not None:
        measurements["point"] = measure_section_point(segments, axis, value, point, precision=precision)
    return measurements


def measure_section_region(
    segments: list[Segment2D],
    axis: int,
    value: float,
    region: tuple[tuple[float, float], tuple[float, float]],
    precision: int = 4,
) -> dict:
    """Measure section contour interaction with a 2D region in section axes."""
    (u0, v0), (u1, v1) = region
    u_min, u_max = sorted((float(u0), float(u1)))
    v_min, v_max = sorted((float(v0), float(v1)))
    rect = (u_min, v_min, u_max, v_max)
    inside_points = [
        p for seg in segments for p in seg
        if _point_in_rect(p, rect)
    ]
    intersecting_segments = [
        seg for seg in segments
        if _segment_intersects_rect(seg, rect)
    ]
    result = {
        "ok": True,
        "axis": _AXIS_NAME[axis],
        "value": round(value, precision),
        "region": [[round(u_min, precision), round(v_min, precision)],
                   [round(u_max, precision), round(v_max, precision)]],
        "u_label": _PLANE_LABELS[axis][0],
        "v_label": _PLANE_LABELS[axis][1],
        "endpoint_count": len(inside_points),
        "intersecting_segment_count": len(intersecting_segments),
        "has_contour_intersection": bool(inside_points or intersecting_segments),
        "inside_point_bbox": _bbox_payload(inside_points, precision) if inside_points else None,
        "intersecting_analysis": analyze_section_segments(intersecting_segments, axis, value, precision),
        "note": "region measures section contours, not filled-volume containment",
    }
    warnings = []
    if not result["has_contour_intersection"]:
        warnings.append("region_has_no_section_contour")
    result["warnings"] = warnings
    return result


def measure_section_line(
    segments: list[Segment2D],
    axis: int,
    value: float,
    line_axis: str,
    line_value: float,
    precision: int = 4,
) -> dict:
    """Intersect a section contour with a fixed-U or fixed-V line."""
    if line_axis not in ("u", "v"):
        raise ValueError("line_axis must be 'u' or 'v'")

    crossings: list[float] = []
    overlapping: list[list[float]] = []
    line_value = float(line_value)
    for p1, p2 in segments:
        fixed1 = p1[0] if line_axis == "u" else p1[1]
        fixed2 = p2[0] if line_axis == "u" else p2[1]
        measure1 = p1[1] if line_axis == "u" else p1[0]
        measure2 = p2[1] if line_axis == "u" else p2[0]
        d1 = fixed1 - line_value
        d2 = fixed2 - line_value

        if abs(d1) < 1e-8 and abs(d2) < 1e-8:
            lo, hi = sorted((measure1, measure2))
            overlapping.append([round(lo, precision), round(hi, precision)])
            crossings.extend([measure1, measure2])
        elif abs(d1) < 1e-8:
            crossings.append(measure1)
        elif abs(d2) < 1e-8:
            crossings.append(measure2)
        elif (d1 < 0) != (d2 < 0):
            t = d1 / (d1 - d2)
            crossings.append(measure1 + t * (measure2 - measure1))

    intersections = _unique_sorted(crossings, precision)
    intervals = [
        [intersections[i], intersections[i + 1]]
        for i in range(0, len(intersections) - 1, 2)
    ]
    gaps = [
        [intervals[i][1], intervals[i + 1][0]]
        for i in range(len(intervals) - 1)
        if intervals[i + 1][0] > intervals[i][1]
    ]
    fixed_label = _PLANE_LABELS[axis][0 if line_axis == "u" else 1]
    measure_label = _PLANE_LABELS[axis][1 if line_axis == "u" else 0]
    result = {
        "ok": True,
        "axis": _AXIS_NAME[axis],
        "section_value": round(value, precision),
        "line_axis": line_axis,
        "line_value": round(line_value, precision),
        "fixed_label": fixed_label,
        "measured_label": measure_label,
        "intersection_count": len(intersections),
        "intersections": intersections,
        "overlapping_segments": overlapping,
        "span": {
            "min": intersections[0] if intersections else None,
            "max": intersections[-1] if intersections else None,
            "size": round(intersections[-1] - intersections[0], precision) if len(intersections) >= 2 else 0.0,
        },
        "filled_intervals_estimate": intervals,
        "gaps_between_intervals": gaps,
        "note": "intervals are paired contour intersections; verify component warnings for complex sections",
        "warnings": [],
    }
    if len(intersections) % 2 == 1:
        result["warnings"].append("odd_intersection_count")
    if not intersections:
        result["warnings"].append("line_has_no_section_intersections")
    return result


def measure_section_point(
    segments: list[Segment2D],
    axis: int,
    value: float,
    point: tuple[float, float],
    precision: int = 4,
) -> dict:
    """Measure nearest contour distance from a point in section coordinates."""
    u, v = float(point[0]), float(point[1])
    if not segments:
        return {
            "ok": False,
            "axis": _AXIS_NAME[axis],
            "section_value": round(value, precision),
            "point": [round(u, precision), round(v, precision)],
            "error": {
                "type": "SectionEmpty",
                "message": "section has no segments",
            },
        }

    best: tuple[float, tuple[float, float], int] | None = None
    for index, segment in enumerate(segments):
        nearest = _nearest_point_on_segment((u, v), segment)
        dist = math.hypot(nearest[0] - u, nearest[1] - v)
        if best is None or dist < best[0]:
            best = (dist, nearest, index)

    assert best is not None
    bbox = _bbox_payload([p for seg in segments for p in seg], precision)
    return {
        "ok": True,
        "axis": _AXIS_NAME[axis],
        "section_value": round(value, precision),
        "point": [round(u, precision), round(v, precision)],
        "u_label": _PLANE_LABELS[axis][0],
        "v_label": _PLANE_LABELS[axis][1],
        "nearest_distance_mm": round(best[0], precision),
        "nearest_point": [round(best[1][0], precision), round(best[1][1], precision)],
        "nearest_segment_index": best[2],
        "inside_section_bbox": bbox["u_min"] <= u <= bbox["u_max"] and bbox["v_min"] <= v <= bbox["v_max"],
        "note": "distance is to the section contour, not a filled-volume inside/outside test",
    }


def _unique_sorted(values: list[float], precision: int) -> list[float]:
    rounded = sorted(round(v, precision) for v in values)
    unique: list[float] = []
    for value in rounded:
        if not unique or abs(value - unique[-1]) > 10 ** (-precision):
            unique.append(value)
    return unique


def _point_in_rect(point: tuple[float, float], rect: tuple[float, float, float, float]) -> bool:
    u_min, v_min, u_max, v_max = rect
    return u_min <= point[0] <= u_max and v_min <= point[1] <= v_max


def _segment_intersects_rect(segment: Segment2D, rect: tuple[float, float, float, float]) -> bool:
    p1, p2 = segment
    u_min, v_min, u_max, v_max = rect
    if _point_in_rect(p1, rect) or _point_in_rect(p2, rect):
        return True
    if max(p1[0], p2[0]) < u_min or min(p1[0], p2[0]) > u_max:
        return False
    if max(p1[1], p2[1]) < v_min or min(p1[1], p2[1]) > v_max:
        return False
    corners = ((u_min, v_min), (u_max, v_min), (u_max, v_max), (u_min, v_max))
    edges = tuple(zip(corners, corners[1:] + corners[:1]))
    return any(_segments_intersect(p1, p2, edge[0], edge[1]) for edge in edges)


def _segments_intersect(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> bool:
    def orient(p: tuple[float, float], q: tuple[float, float], r: tuple[float, float]) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    o1 = orient(a, b, c)
    o2 = orient(a, b, d)
    o3 = orient(c, d, a)
    o4 = orient(c, d, b)
    if (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0):
        return True
    eps = 1e-8
    return (
        abs(o1) < eps and _point_on_segment(c, a, b)
        or abs(o2) < eps and _point_on_segment(d, a, b)
        or abs(o3) < eps and _point_on_segment(a, c, d)
        or abs(o4) < eps and _point_on_segment(b, c, d)
    )


def _point_on_segment(
    point: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
) -> bool:
    eps = 1e-8
    return (
        min(a[0], b[0]) - eps <= point[0] <= max(a[0], b[0]) + eps
        and min(a[1], b[1]) - eps <= point[1] <= max(a[1], b[1]) + eps
    )


def _nearest_point_on_segment(point: tuple[float, float], segment: Segment2D) -> tuple[float, float]:
    (u, v), (u2, v2) = segment
    du = u2 - u
    dv = v2 - v
    length_sq = du * du + dv * dv
    if length_sq < 1e-12:
        return (u, v)
    t = ((point[0] - u) * du + (point[1] - v) * dv) / length_sq
    t = max(0.0, min(1.0, t))
    return (u + t * du, v + t * dv)
