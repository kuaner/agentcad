"""Cross-section extraction and 2D SVG rendering from STL meshes.

Slices a 3D mesh with an axis-aligned plane and returns either raw line
segments (for numerical analysis) or an SVG string (for visual inspection
with LLM vision tools).  Supports X, Y, and Z cutting planes.
"""
from __future__ import annotations

import math
from pathlib import Path

from .jsonio import write_json
from .stl import Triangle

# Axis constants — match array index in 3D vertex tuples.
AXIS_X = 0
AXIS_Y = 1
AXIS_Z = 2

# 2D plane labels: (horizontal_axis_label, vertical_axis_label, plane_name)
_PLANE_LABELS: dict[int, tuple[str, str, str]] = {
    AXIS_X: ("Y (mm)", "Z (mm)", "YZ plane"),
    AXIS_Y: ("X (mm)", "Z (mm)", "XZ plane"),
    AXIS_Z: ("X (mm)", "Y (mm)", "XY plane"),
}
_AXIS_NAME = {AXIS_X: "X", AXIS_Y: "Y", AXIS_Z: "Z"}

Segment2D = tuple[tuple[float, float], tuple[float, float]]


# ── Segment extraction ────────────────────────────────────────────────────────

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


# ── Profile scan ─────────────────────────────────────────────────────────────

def scan_profile(
    triangles: list[Triangle],
    axis: int = AXIS_Z,
    samples: int = 20,
    step_threshold: float = 2.0,
) -> dict:
    """Scan the mesh along an axis, measuring cross-section size at each position.

    At each sampled position, slices the mesh and reports the 2D bounding box
    of the intersection.  Detects *step changes* — positions where the section
    size changes abruptly — which mark feature boundaries (cavity starts, port
    openings, wall ends, etc.).

    Args:
        triangles: STL triangle list.
        axis: 0=X, 1=Y, 2=Z (scanning direction).
        samples: Number of evenly-spaced cross-sections to take.
        step_threshold: Minimum size change (mm) to count as a step change.

    Returns a dict with ``profile`` (list of per-position measurements) and
    ``step_changes`` (list of detected boundary positions).
    """
    if not triangles:
        return {"ok": False, "error": "no triangles"}

    all_vals = [v[axis] for tri in triangles for v in tri]
    pos_min = min(all_vals)
    pos_max = max(all_vals)

    if pos_max - pos_min < 1e-6:
        return {"ok": False, "error": f"zero extent along {_AXIS_NAME[axis]} axis"}

    margin = (pos_max - pos_min) * 0.02
    span = pos_max - pos_min - 2 * margin
    positions = [pos_min + margin + span * i / max(samples - 1, 1) for i in range(samples)]

    profile = []
    for pos in positions:
        segs = section_segments(triangles, axis, pos)
        if not segs:
            profile.append({
                "pos": round(pos, 3),
                "point_count": 0,
                "u_size": 0.0,
                "v_size": 0.0,
            })
            continue

        us = [p[0] for seg in segs for p in seg]
        vs = [p[1] for seg in segs for p in seg]
        u_size = max(us) - min(us)
        v_size = max(vs) - min(vs)
        profile.append({
            "pos": round(pos, 3),
            "point_count": len(segs) * 2,
            "u_size": round(u_size, 3),
            "v_size": round(v_size, 3),
            "u_min": round(min(us), 3),
            "u_max": round(max(us), 3),
            "v_min": round(min(vs), 3),
            "v_max": round(max(vs), 3),
        })

    # Point count threshold: catches hollow shells where outer bbox is constant
    # but interior surfaces appear (e.g. phone case cavity starting).
    max_pts = max((p["point_count"] for p in profile), default=1) or 1
    count_threshold = max(30, max_pts * 0.04)

    step_changes = []
    for i in range(1, len(profile)):
        prev = profile[i - 1]
        curr = profile[i]
        du = curr["u_size"] - prev["u_size"]
        dv = curr["v_size"] - prev["v_size"]
        dpts = curr["point_count"] - prev["point_count"]
        size_step = abs(du) > step_threshold or abs(dv) > step_threshold
        count_step = abs(dpts) >= count_threshold
        if size_step or count_step:
            pos_mid = round((prev["pos"] + curr["pos"]) / 2, 3)
            step_changes.append({
                "pos": pos_mid,
                "delta_u": round(du, 3),
                "delta_v": round(dv, 3),
                "delta_point_count": dpts,
                "hint": _step_hint(du, dv, dpts),
            })

    u_lbl, v_lbl, plane_lbl = _PLANE_LABELS[axis]
    return {
        "ok": True,
        "axis": _AXIS_NAME[axis],
        "plane_label": plane_lbl,
        "u_label": u_lbl,
        "v_label": v_lbl,
        "pos_range": [round(pos_min, 3), round(pos_max, 3)],
        "profile": profile,
        "step_changes": step_changes,
    }


def _step_hint(du: float, dv: float, dpts: int = 0) -> str:
    if du < -2 or dv < -2:
        return "section shrinks — possible cavity start or wall end"
    if du > 2 or dv > 2:
        return "section grows — possible feature addition or flange"
    if dpts > 0:
        return "more interior surfaces — inner cavity or new features begin here"
    if dpts < 0:
        return "fewer interior surfaces — inner cavity or features end here"
    return "geometry transition"


# ── Section measurement ──────────────────────────────────────────────────────

def analyze_section_segments(
    segments: list[Segment2D],
    axis: int,
    value: float,
    precision: int = 4,
) -> dict:
    """Measure a 2D section numerically.

    SVGs are useful for visual review, but agents need structured geometry to
    decide whether a section is plausible without relying on image perception.
    This reports global bbox facts plus connected loop/component facts.
    """
    u_lbl, v_lbl, plane_lbl = _PLANE_LABELS[axis]
    base = {
        "ok": True,
        "axis": _AXIS_NAME[axis],
        "value": round(value, precision),
        "plane_label": plane_lbl,
        "u_label": u_lbl,
        "v_label": v_lbl,
        "segment_count": len(segments),
        "point_count": len(segments) * 2,
    }
    if not segments:
        return {
            **base,
            "bbox": None,
            "total_segment_length_mm": 0.0,
            "component_count": 0,
            "components": [],
            "warnings": ["empty_section"],
        }

    all_points = [p for seg in segments for p in seg]
    graph: dict[tuple[float, float], set[tuple[float, float]]] = {}
    edges: list[tuple[tuple[float, float], tuple[float, float], float]] = []

    for p1, p2 in segments:
        k1 = _point_key(p1, precision)
        k2 = _point_key(p2, precision)
        graph.setdefault(k1, set())
        graph.setdefault(k2, set())
        length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        edges.append((k1, k2, length))
        if k1 != k2:
            graph[k1].add(k2)
            graph[k2].add(k1)

    components = _section_components(graph, edges, precision)
    warnings: list[str] = []
    if len(components) > 1:
        warnings.append("multiple_section_components")
    if any(c["segment_count"] < 3 for c in components):
        warnings.append("sparse_section_component")
    if any(c["closed_vertex_ratio"] < 0.75 and c["segment_count"] >= 3 for c in components):
        warnings.append("open_section_component")

    return {
        **base,
        "bbox": _bbox_payload(all_points, precision),
        "total_segment_length_mm": round(sum(edge[2] for edge in edges), precision),
        "component_count": len(components),
        "components": components,
        "warnings": warnings,
    }


def _section_components(
    graph: dict[tuple[float, float], set[tuple[float, float]]],
    edges: list[tuple[tuple[float, float], tuple[float, float], float]],
    precision: int,
) -> list[dict]:
    remaining = set(graph)
    components = []
    while remaining:
        start = remaining.pop()
        stack = [start]
        vertices = {start}
        while stack:
            node = stack.pop()
            for neighbor in graph.get(node, set()):
                if neighbor in vertices:
                    continue
                vertices.add(neighbor)
                remaining.discard(neighbor)
                stack.append(neighbor)

        comp_edges = [edge for edge in edges if edge[0] in vertices and edge[1] in vertices]
        points = sorted(vertices)
        bbox = _bbox_payload(points, precision)
        degrees = [len(graph.get(point, set())) for point in points]
        closed_count = sum(1 for degree in degrees if degree == 2)
        component = {
            "index": len(components),
            "segment_count": len(comp_edges),
            "point_count": len(points),
            "bbox": bbox,
            "centroid": [
                round(sum(p[0] for p in points) / len(points), precision),
                round(sum(p[1] for p in points) / len(points), precision),
            ],
            "total_segment_length_mm": round(sum(edge[2] for edge in comp_edges), precision),
            "hull_area_estimate_mm2": round(_convex_hull_area(points), precision),
            "closed_vertex_ratio": round(closed_count / max(len(points), 1), precision),
            "endpoint_count": sum(1 for degree in degrees if degree == 1),
            "branch_vertex_count": sum(1 for degree in degrees if degree > 2),
        }
        components.append(component)

    components.sort(key=lambda c: c["hull_area_estimate_mm2"], reverse=True)
    for index, component in enumerate(components):
        component["index"] = index
    return components


def _point_key(point: tuple[float, float], precision: int) -> tuple[float, float]:
    return (round(point[0], precision), round(point[1], precision))


def _bbox_payload(points: list[tuple[float, float]], precision: int) -> dict:
    us = [p[0] for p in points]
    vs = [p[1] for p in points]
    u_min, u_max = min(us), max(us)
    v_min, v_max = min(vs), max(vs)
    return {
        "u_min": round(u_min, precision),
        "u_max": round(u_max, precision),
        "v_min": round(v_min, precision),
        "v_max": round(v_max, precision),
        "u_size": round(u_max - u_min, precision),
        "v_size": round(v_max - v_min, precision),
    }


def _convex_hull_area(points: list[tuple[float, float]]) -> float:
    unique = sorted(set(points))
    if len(unique) < 3:
        return 0.0

    def cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)

    upper: list[tuple[float, float]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)

    hull = lower[:-1] + upper[:-1]
    return abs(sum(
        hull[i][0] * hull[(i + 1) % len(hull)][1]
        - hull[(i + 1) % len(hull)][0] * hull[i][1]
        for i in range(len(hull))
    )) / 2.0


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
            "error": "section has no segments",
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


# ── SVG rendering ─────────────────────────────────────────────────────────────

def render_section_svg(
    segments: list[Segment2D],
    axis: int,
    value: float,
    canvas: int = 500,
    padding: int = 48,
) -> str:
    """Render cross-section line segments as an SVG string.

    The SVG is suitable for LLM vision inspection: dark lines on white
    background, annotated with axis labels, corner coordinates, and a scale bar.
    """
    u_lbl, v_lbl, plane_lbl = _PLANE_LABELS[axis]
    axis_name = _AXIS_NAME[axis]
    title = f"{axis_name} = {value:.2f} mm  ·  {plane_lbl}"

    if not segments:
        return _empty_svg(canvas, title)

    all_u = [p[0] for seg in segments for p in seg]
    all_v = [p[1] for seg in segments for p in seg]
    u_min, u_max = min(all_u), max(all_u)
    v_min, v_max = min(all_v), max(all_v)
    u_range = max(u_max - u_min, 1.0)
    v_range = max(v_max - v_min, 1.0)

    draw = canvas - 2 * padding
    scale = min(draw / u_range, draw / v_range)
    aw = u_range * scale
    ah = v_range * scale
    ox = padding + (draw - aw) / 2
    oy = padding + (draw - ah) / 2

    def to_svg(u: float, v: float) -> tuple[float, float]:
        return ox + (u - u_min) * scale, oy + ah - (v - v_min) * scale

    lines = []
    for (u1, v1), (u2, v2) in segments:
        x1, y1 = to_svg(u1, v1)
        x2, y2 = to_svg(u2, v2)
        lines.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="#1a1a2e" stroke-width="1.2" stroke-linecap="round"/>'
        )

    # Corner coordinate labels
    def txt(x: float, y: float, s: str, anchor: str = "middle") -> str:
        return (
            f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
            f'font-size="9" fill="#777" font-family="monospace">{s}</text>'
        )

    cw = canvas
    labels = [
        txt(ox,          oy + ah + 14, f"{u_min:.1f}", "start"),
        txt(ox + aw,     oy + ah + 14, f"{u_max:.1f}", "end"),
        txt(ox - 4,      oy + ah,      f"{v_min:.1f}", "end"),
        txt(ox - 4,      oy,           f"{v_max:.1f}", "end"),
        txt(ox + aw / 2, cw - 6,       u_lbl),
        (f'<text x="12" y="{oy + ah / 2:.1f}" text-anchor="middle" font-size="9" '
         f'fill="#777" font-family="sans-serif" '
         f'transform="rotate(-90 12 {oy + ah / 2:.1f})">{v_lbl}</text>'),
    ]

    # Scale bar
    bar_mm = _nice_bar(u_range)
    bar_px = bar_mm * scale
    bx = ox + aw - bar_px
    by = oy + ah + 26
    scale_bar = (
        f'<line x1="{bx:.1f}" y1="{by}" x2="{bx + bar_px:.1f}" y2="{by}" '
        f'stroke="#999" stroke-width="1.5"/>'
        f'<text x="{bx + bar_px / 2:.1f}" y="{by + 11}" text-anchor="middle" '
        f'font-size="9" fill="#999" font-family="sans-serif">{bar_mm:.0f} mm</text>'
    )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{cw}" height="{cw}">'
        f'<rect width="{cw}" height="{cw}" fill="white" rx="3"/>'
        f'<rect x="{ox:.1f}" y="{oy:.1f}" width="{aw:.1f}" height="{ah:.1f}" '
        f'fill="#f5f5f7" stroke="#e0e0e0" stroke-width="0.5"/>'
        f'<text x="{cw // 2}" y="18" text-anchor="middle" font-size="11" '
        f'font-weight="600" fill="#333" font-family="sans-serif">{title}</text>'
        f'<g>{"".join(lines)}</g>'
        f'{"".join(labels)}'
        f'{scale_bar}'
        f'</svg>'
    )


def write_section_svg(
    triangles: list[Triangle],
    axis: int,
    value: float,
    out_path: Path,
    canvas: int = 500,
    analysis_path: Path | None = None,
    write_analysis: bool = True,
) -> dict:
    """Extract section, render SVG, and write measured sidecar JSON."""
    segs = section_segments(triangles, axis, value)
    svg = render_section_svg(segs, axis, value, canvas=canvas)
    analysis = analyze_section_segments(segs, axis, value)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(svg, encoding="utf-8")
    analysis_payload = {
        "stage": "section_analysis",
        "svg": str(out_path),
        **analysis,
    }
    analysis_json = None
    if write_analysis:
        analysis_path = analysis_path or out_path.with_suffix(".json")
        write_json(analysis_path, analysis_payload)
        analysis_json = str(analysis_path)
    return {
        "ok": True,
        "axis": _AXIS_NAME[axis],
        "value": value,
        "segment_count": len(segs),
        "svg": str(out_path),
        "analysis": analysis_payload,
        "analysis_json": analysis_json,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _nice_bar(total_range: float) -> float:
    for v in (1, 2, 5, 10, 20, 50, 100, 200):
        if total_range / v <= 6:
            return float(v)
    return 200.0


def _empty_svg(canvas: int, title: str) -> str:
    mid = canvas // 2
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas}" height="{canvas}">'
        f'<rect width="{canvas}" height="{canvas}" fill="white" rx="3"/>'
        f'<text x="{mid}" y="18" text-anchor="middle" font-size="11" '
        f'font-weight="600" fill="#333" font-family="sans-serif">{title}</text>'
        f'<text x="{mid}" y="{mid}" text-anchor="middle" font-size="13" '
        f'fill="#bbb" font-family="sans-serif">no intersections at this section</text>'
        f'</svg>'
    )
