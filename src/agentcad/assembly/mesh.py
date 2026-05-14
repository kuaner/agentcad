from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

from ..stl import Triangle, Vec3, cross, dot, length, normalize, sub
from .types import EPS


@dataclass
class _TriBvhNode:
    bbox: tuple[Vec3, Vec3]
    indices: list[int] | None = None
    left: "_TriBvhNode | None" = None
    right: "_TriBvhNode | None" = None


def _add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(v: Vec3, scalar: float) -> Vec3:
    return (v[0] * scalar, v[1] * scalar, v[2] * scalar)


def _round_vec(value, digits: int = 6) -> list[float]:
    return [round(float(v), digits) for v in value]


def _measure_pairwise(components: dict[str, dict]) -> list[dict]:
    rows = []
    for a_id, b_id in itertools.combinations(sorted(components), 2):
        component_a = components[a_id]
        component_b = components[b_id]
        bbox_a = components[a_id].get("world_bbox")
        bbox_b = components[b_id].get("world_bbox")
        bbox_overlap = _bbox_overlap(bbox_a, bbox_b)
        aabb_clearance = _bbox_clearance(bbox_a, bbox_b)
        narrow = _mesh_pair_evidence(
            component_a.get("world_triangles") or [],
            component_b.get("world_triangles") or [],
            bbox_overlap=bbox_overlap,
            aabb_clearance=aabb_clearance,
        )
        rows.append(
            {
                "components": [a_id, b_id],
                "bbox_overlap": bbox_overlap,
                "aabb_clearance_mm": aabb_clearance,
                **narrow,
            }
        )
    return rows


def _mesh_pair_evidence(
    triangles_a: list[Triangle],
    triangles_b: list[Triangle],
    *,
    bbox_overlap: bool,
    aabb_clearance: float | None,
) -> dict:
    if not triangles_a or not triangles_b:
        return {
            "method": "mesh_narrow_phase_unavailable",
            "mesh_clearance_mm": None,
            "mesh_penetration_mm": None,
            "interferes": False,
            "narrow_phase": {
                "ok": False,
                "error": {"type": "MeshMissing", "message": "both components need STL triangles for narrow-phase evidence"},
            },
        }
    if not bbox_overlap:
        return {
            "method": "aabb_separated",
            "mesh_clearance_mm": aabb_clearance,
            "mesh_penetration_mm": 0.0,
            "interferes": False,
            "narrow_phase": {
                "ok": True,
                "broad_phase": "separated",
                "triangle_intersection_count": 0,
                "inside_sample_count": 0,
                "min_sample_distance_mm": aabb_clearance,
            },
        }

    evidence = _narrow_phase_mesh_pair(triangles_a, triangles_b)
    penetration = float(evidence.get("max_penetration_mm") or 0.0)
    triangle_hits = int(evidence.get("triangle_intersection_count") or 0)
    clearance = -penetration if penetration > EPS else (0.0 if triangle_hits else evidence.get("min_sample_distance_mm"))
    return {
        "method": "mesh_narrow_phase_v1",
        "mesh_clearance_mm": clearance,
        "mesh_penetration_mm": penetration,
        "interferes": penetration > EPS,
        "narrow_phase": evidence,
    }


def _narrow_phase_mesh_pair(triangles_a: list[Triangle], triangles_b: list[Triangle]) -> dict:
    boxes_a = [_triangle_aabb(tri) for tri in triangles_a]
    boxes_b = [_triangle_aabb(tri) for tri in triangles_b]
    candidate_pairs = list(_overlapping_triangle_pairs(boxes_a, boxes_b))
    triangle_intersections = 0
    for i, j in candidate_pairs:
        if _triangles_intersect(triangles_a[i], triangles_b[j]):
            triangle_intersections += 1
            if triangle_intersections >= 256:
                break

    samples_a = _mesh_sample_points(triangles_a)
    samples_b = _mesh_sample_points(triangles_b)
    inside: list[dict] = []
    min_distance: float | None = None

    for owner, samples, other in (("a", samples_a, triangles_b), ("b", samples_b, triangles_a)):
        for point in samples:
            distance = _point_mesh_distance(point, other)
            if min_distance is None or distance < min_distance:
                min_distance = distance
            if distance > 1e-5 and _point_inside_mesh(point, other):
                inside.append(
                    {
                        "owner": owner,
                        "point": _round_vec(point),
                        "penetration_mm": distance,
                    }
                )

    max_penetration = max((row["penetration_mm"] for row in inside), default=0.0)
    deepest = max(inside, key=lambda row: row["penetration_mm"], default=None)
    return {
        "ok": True,
        "broad_phase": "aabb_overlap",
        "triangle_candidate_pairs": len(candidate_pairs),
        "triangle_intersection_count": triangle_intersections,
        "inside_sample_count": len(inside),
        "sample_count": len(samples_a) + len(samples_b),
        "min_sample_distance_mm": min_distance,
        "max_penetration_mm": max_penetration,
        "deepest_sample": deepest,
        "note": "inside samples estimate solid penetration; triangle intersections without inside samples are treated as surface contact evidence",
    }


def _mesh_sample_points(triangles: list[Triangle], max_samples: int = 384) -> list[Vec3]:
    points: list[Vec3] = []
    for tri in triangles:
        points.extend(tri)
        points.append(_triangle_centroid(tri))
    dedup: list[Vec3] = []
    seen: set[Vec3] = set()
    for point in points:
        key = (round(point[0], 4), round(point[1], 4), round(point[2], 4))
        if key in seen:
            continue
        seen.add(key)
        dedup.append(point)
    if len(dedup) <= max_samples:
        return dedup
    step = len(dedup) / max_samples
    return [dedup[min(int(i * step), len(dedup) - 1)] for i in range(max_samples)]


def _triangle_centroid(tri: Triangle) -> Vec3:
    return (
        (tri[0][0] + tri[1][0] + tri[2][0]) / 3.0,
        (tri[0][1] + tri[1][1] + tri[2][1]) / 3.0,
        (tri[0][2] + tri[1][2] + tri[2][2]) / 3.0,
    )


def _triangle_aabb(tri: Triangle) -> tuple[Vec3, Vec3]:
    return (
        (min(p[0] for p in tri), min(p[1] for p in tri), min(p[2] for p in tri)),
        (max(p[0] for p in tri), max(p[1] for p in tri), max(p[2] for p in tri)),
    )


def _overlapping_triangle_pairs(
    boxes_a: list[tuple[Vec3, Vec3]],
    boxes_b: list[tuple[Vec3, Vec3]],
) -> list[tuple[int, int]]:
    if not boxes_a or not boxes_b:
        return []
    tree_a = _build_tri_bvh(boxes_a, list(range(len(boxes_a))))
    tree_b = _build_tri_bvh(boxes_b, list(range(len(boxes_b))))
    pairs: list[tuple[int, int]] = []
    _collect_bvh_pairs(tree_a, tree_b, boxes_a, boxes_b, pairs)
    return pairs


def _build_tri_bvh(boxes: list[tuple[Vec3, Vec3]], indices: list[int]) -> _TriBvhNode:
    bbox = _union_box([boxes[index] for index in indices])
    if len(indices) <= 24:
        return _TriBvhNode(bbox=bbox, indices=indices)
    spans = [bbox[1][axis] - bbox[0][axis] for axis in range(3)]
    axis = max(range(3), key=lambda item: spans[item])
    indices.sort(key=lambda index: (boxes[index][0][axis] + boxes[index][1][axis]) / 2.0)
    mid = max(1, min(len(indices) - 1, len(indices) // 2))
    return _TriBvhNode(
        bbox=bbox,
        left=_build_tri_bvh(boxes, indices[:mid]),
        right=_build_tri_bvh(boxes, indices[mid:]),
    )


def _collect_bvh_pairs(
    a: _TriBvhNode,
    b: _TriBvhNode,
    boxes_a: list[tuple[Vec3, Vec3]],
    boxes_b: list[tuple[Vec3, Vec3]],
    pairs: list[tuple[int, int]],
) -> None:
    if not _boxes_overlap(a.bbox, b.bbox):
        return
    if a.indices is not None and b.indices is not None:
        for i in a.indices:
            for j in b.indices:
                if _boxes_overlap(boxes_a[i], boxes_b[j]):
                    pairs.append((i, j))
        return
    if b.indices is not None or (a.indices is None and _box_volume(a.bbox) >= _box_volume(b.bbox)):
        if a.left is not None:
            _collect_bvh_pairs(a.left, b, boxes_a, boxes_b, pairs)
        if a.right is not None:
            _collect_bvh_pairs(a.right, b, boxes_a, boxes_b, pairs)
    else:
        if b.left is not None:
            _collect_bvh_pairs(a, b.left, boxes_a, boxes_b, pairs)
        if b.right is not None:
            _collect_bvh_pairs(a, b.right, boxes_a, boxes_b, pairs)


def _union_box(boxes: list[tuple[Vec3, Vec3]]) -> tuple[Vec3, Vec3]:
    return (
        (min(box[0][0] for box in boxes), min(box[0][1] for box in boxes), min(box[0][2] for box in boxes)),
        (max(box[1][0] for box in boxes), max(box[1][1] for box in boxes), max(box[1][2] for box in boxes)),
    )


def _boxes_overlap(a: tuple[Vec3, Vec3], b: tuple[Vec3, Vec3], eps: float = 1e-8) -> bool:
    return all(a[0][axis] <= b[1][axis] + eps and b[0][axis] <= a[1][axis] + eps for axis in range(3))


def _box_volume(box: tuple[Vec3, Vec3]) -> float:
    return max(box[1][0] - box[0][0], 0.0) * max(box[1][1] - box[0][1], 0.0) * max(box[1][2] - box[0][2], 0.0)


def _triangles_intersect(a: Triangle, b: Triangle) -> bool:
    for p, q in ((a[0], a[1]), (a[1], a[2]), (a[2], a[0])):
        if _segment_triangle_intersects(p, q, b):
            return True
    for p, q in ((b[0], b[1]), (b[1], b[2]), (b[2], b[0])):
        if _segment_triangle_intersects(p, q, a):
            return True
    return _coplanar_triangles_overlap(a, b)


def _segment_triangle_intersects(p0: Vec3, p1: Vec3, tri: Triangle, eps: float = 1e-9) -> bool:
    direction = sub(p1, p0)
    edge1 = sub(tri[1], tri[0])
    edge2 = sub(tri[2], tri[0])
    h = cross(direction, edge2)
    det = dot(edge1, h)
    if abs(det) < eps:
        return False
    inv_det = 1.0 / det
    s = sub(p0, tri[0])
    u = inv_det * dot(s, h)
    if u < -eps or u > 1.0 + eps:
        return False
    q = cross(s, edge1)
    v = inv_det * dot(direction, q)
    if v < -eps or u + v > 1.0 + eps:
        return False
    t = inv_det * dot(edge2, q)
    return -eps <= t <= 1.0 + eps


def _coplanar_triangles_overlap(a: Triangle, b: Triangle, eps: float = 1e-7) -> bool:
    normal_a = cross(sub(a[1], a[0]), sub(a[2], a[0]))
    normal_b = cross(sub(b[1], b[0]), sub(b[2], b[0]))
    if length(normal_a) <= eps or length(normal_b) <= eps:
        return False
    na = normalize(normal_a)
    nb = normalize(normal_b)
    if abs(abs(dot(na, nb)) - 1.0) > 1e-5:
        return False
    if any(abs(dot(sub(point, a[0]), na)) > eps for point in b):
        return False
    drop = max(range(3), key=lambda axis: abs(na[axis]))
    pa = [_project2(point, drop) for point in a]
    pb = [_project2(point, drop) for point in b]
    for e1 in ((pa[0], pa[1]), (pa[1], pa[2]), (pa[2], pa[0])):
        for e2 in ((pb[0], pb[1]), (pb[1], pb[2]), (pb[2], pb[0])):
            if _segments_intersect_2d(e1[0], e1[1], e2[0], e2[1]):
                return True
    return _point_in_triangle_2d(pa[0], pb) or _point_in_triangle_2d(pb[0], pa)


def _project2(point: Vec3, drop_axis: int) -> tuple[float, float]:
    axes = [axis for axis in (0, 1, 2) if axis != drop_axis]
    return (point[axes[0]], point[axes[1]])


def _segments_intersect_2d(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
    eps: float = 1e-9,
) -> bool:
    def orient(p: tuple[float, float], q: tuple[float, float], r: tuple[float, float]) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    o1 = orient(a, b, c)
    o2 = orient(a, b, d)
    o3 = orient(c, d, a)
    o4 = orient(c, d, b)
    if (o1 > eps) != (o2 > eps) and (o3 > eps) != (o4 > eps):
        return True
    return (
        abs(o1) <= eps and _point_on_segment_2d(c, a, b, eps)
        or abs(o2) <= eps and _point_on_segment_2d(d, a, b, eps)
        or abs(o3) <= eps and _point_on_segment_2d(a, c, d, eps)
        or abs(o4) <= eps and _point_on_segment_2d(b, c, d, eps)
    )


def _point_on_segment_2d(
    point: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
    eps: float,
) -> bool:
    return (
        min(a[0], b[0]) - eps <= point[0] <= max(a[0], b[0]) + eps
        and min(a[1], b[1]) - eps <= point[1] <= max(a[1], b[1]) + eps
    )


def _point_in_triangle_2d(point: tuple[float, float], tri: list[tuple[float, float]], eps: float = 1e-9) -> bool:
    a, b, c = tri
    area = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    if abs(area) <= eps:
        return False
    s = ((a[1] - c[1]) * (point[0] - c[0]) + (c[0] - a[0]) * (point[1] - c[1])) / area
    t = ((c[1] - b[1]) * (point[0] - c[0]) + (b[0] - c[0]) * (point[1] - c[1])) / area
    u = 1.0 - s - t
    return s >= -eps and t >= -eps and u >= -eps


def _point_mesh_distance(point: Vec3, triangles: list[Triangle]) -> float:
    return min((_point_triangle_distance(point, tri) for tri in triangles), default=float("inf"))


def _point_triangle_distance(point: Vec3, tri: Triangle) -> float:
    # Real-Time Collision Detection, closest point on triangle.
    a, b, c = tri
    ab = sub(b, a)
    ac = sub(c, a)
    ap = sub(point, a)
    d1 = dot(ab, ap)
    d2 = dot(ac, ap)
    if d1 <= 0.0 and d2 <= 0.0:
        return length(sub(point, a))

    bp = sub(point, b)
    d3 = dot(ab, bp)
    d4 = dot(ac, bp)
    if d3 >= 0.0 and d4 <= d3:
        return length(sub(point, b))

    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        v = d1 / (d1 - d3)
        nearest = _add(a, _mul(ab, v))
        return length(sub(point, nearest))

    cp = sub(point, c)
    d5 = dot(ab, cp)
    d6 = dot(ac, cp)
    if d6 >= 0.0 and d5 <= d6:
        return length(sub(point, c))

    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        w = d2 / (d2 - d6)
        nearest = _add(a, _mul(ac, w))
        return length(sub(point, nearest))

    va = d3 * d6 - d5 * d4
    if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        nearest = _add(b, _mul(sub(c, b), w))
        return length(sub(point, nearest))

    n = normalize(cross(ab, ac))
    return abs(dot(sub(point, a), n))


def _point_inside_mesh(point: Vec3, triangles: list[Triangle]) -> bool:
    direction = normalize((0.817137, 0.271828, 0.506731))
    hits: list[float] = []
    for tri in triangles:
        t = _ray_triangle_t(point, direction, tri)
        if t is None or t <= 1e-7:
            continue
        if not any(abs(t - existing) <= 1e-6 for existing in hits):
            hits.append(t)
    return len(hits) % 2 == 1


def _ray_triangle_t(origin: Vec3, direction: Vec3, tri: Triangle, eps: float = 1e-9) -> float | None:
    edge1 = sub(tri[1], tri[0])
    edge2 = sub(tri[2], tri[0])
    h = cross(direction, edge2)
    det = dot(edge1, h)
    if abs(det) < eps:
        return None
    inv_det = 1.0 / det
    s = sub(origin, tri[0])
    u = inv_det * dot(s, h)
    if u < -eps or u > 1.0 + eps:
        return None
    q = cross(s, edge1)
    v = inv_det * dot(direction, q)
    if v < -eps or u + v > 1.0 + eps:
        return None
    t = inv_det * dot(edge2, q)
    return t if t > eps else None


def _bbox_overlap(a: dict | None, b: dict | None) -> bool:
    if not a or not b:
        return False
    return all(a["min"][i] <= b["max"][i] + EPS and b["min"][i] <= a["max"][i] + EPS for i in range(3))


def _bbox_clearance(a: dict | None, b: dict | None) -> float | None:
    if not a or not b:
        return None
    distances = []
    for i in range(3):
        if a["max"][i] < b["min"][i]:
            distances.append(b["min"][i] - a["max"][i])
        elif b["max"][i] < a["min"][i]:
            distances.append(a["min"][i] - b["max"][i])
        else:
            distances.append(0.0)
    return math.sqrt(sum(distance * distance for distance in distances))


def _global_bbox(bboxes: list[dict | None]) -> dict | None:
    valid = [bbox for bbox in bboxes if bbox]
    if not valid:
        return None
    min_v = [min(bbox["min"][i] for bbox in valid) for i in range(3)]
    max_v = [max(bbox["max"][i] for bbox in valid) for i in range(3)]
    return {
        "min": min_v,
        "max": max_v,
        "size": [max_v[i] - min_v[i] for i in range(3)],
        "center": [(max_v[i] + min_v[i]) / 2.0 for i in range(3)],
    }
