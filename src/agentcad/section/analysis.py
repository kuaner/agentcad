from __future__ import annotations

import math

from ..stl import Triangle
from .extraction import section_segments
from .types import AXIS_Z, Segment2D, _AXIS_NAME, _PLANE_LABELS

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
