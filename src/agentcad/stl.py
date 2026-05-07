from __future__ import annotations

import math
import struct
from collections import defaultdict
from pathlib import Path
from typing import Iterable

Vec3 = tuple[float, float, float]
Triangle = tuple[Vec3, Vec3, Vec3]


def sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def length(v: Vec3) -> float:
    return math.sqrt(dot(v, v))


def normalize(v: Vec3) -> Vec3:
    n = length(v)
    if n <= 1e-12:
        return (0.0, 0.0, 1.0)
    return (v[0] / n, v[1] / n, v[2] / n)


def read_stl(path: Path) -> list[Triangle]:
    data = path.read_bytes()
    if len(data) >= 84:
        tri_count = struct.unpack_from("<I", data, 80)[0]
        expected = 84 + tri_count * 50
        if expected == len(data):
            return _read_binary(data, tri_count)
    return _read_ascii(data.decode("utf-8", errors="ignore"))


def _read_binary(data: bytes, tri_count: int) -> list[Triangle]:
    triangles: list[Triangle] = []
    offset = 84
    for _ in range(tri_count):
        offset += 12
        values = struct.unpack_from("<9f", data, offset)
        offset += 36
        offset += 2
        triangles.append(
            (
                (float(values[0]), float(values[1]), float(values[2])),
                (float(values[3]), float(values[4]), float(values[5])),
                (float(values[6]), float(values[7]), float(values[8])),
            )
        )
    return triangles


def _read_ascii(text: str) -> list[Triangle]:
    vertices: list[Vec3] = []
    triangles: list[Triangle] = []
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) == 4 and parts[0].lower() == "vertex":
            vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
            if len(vertices) == 3:
                triangles.append((vertices[0], vertices[1], vertices[2]))
                vertices = []
    return triangles


def triangle_normal(tri: Triangle) -> Vec3:
    a, b, c = tri
    return normalize(cross(sub(b, a), sub(c, a)))


def triangle_area(tri: Triangle) -> float:
    a, b, c = tri
    return 0.5 * length(cross(sub(b, a), sub(c, a)))


def iter_vertices(triangles: Iterable[Triangle]) -> Iterable[Vec3]:
    for tri in triangles:
        yield tri[0]
        yield tri[1]
        yield tri[2]


def mesh_report(triangles: list[Triangle]) -> dict:
    if not triangles:
        return {
            "bbox": None,
            "mesh": {"triangles": 0, "vertices": 0, "watertight": False},
            "mass_properties": {"surface_area": 0.0, "volume": 0.0},
        }

    vertices = list(iter_vertices(triangles))
    min_v = [min(v[i] for v in vertices) for i in range(3)]
    max_v = [max(v[i] for v in vertices) for i in range(3)]
    size = [max_v[i] - min_v[i] for i in range(3)]
    center = [(max_v[i] + min_v[i]) / 2 for i in range(3)]
    surface_area = sum(triangle_area(tri) for tri in triangles)
    signed_volume = 0.0
    for a, b, c in triangles:
        signed_volume += dot(a, cross(b, c)) / 6.0

    edge_counts: dict[tuple[Vec3, Vec3], int] = defaultdict(int)
    for a, b, c in triangles:
        for p, q in ((a, b), (b, c), (c, a)):
            key = tuple(sorted((_round_vertex(p), _round_vertex(q))))  # type: ignore[arg-type]
            edge_counts[key] += 1
    boundary_edges = sum(1 for count in edge_counts.values() if count != 2)

    return {
        "bbox": {
            "min": min_v,
            "max": max_v,
            "size": size,
            "center": center,
        },
        "mesh": {
            "triangles": len(triangles),
            "vertices": len(vertices),
            "unique_edges": len(edge_counts),
            "boundary_or_nonmanifold_edges": boundary_edges,
            "watertight": boundary_edges == 0,
        },
        "mass_properties": {
            "surface_area": surface_area,
            "volume": abs(signed_volume),
        },
    }


def _round_vertex(v: Vec3) -> Vec3:
    return (round(v[0], 6), round(v[1], 6), round(v[2], 6))


def section_radius_at_z(triangles: list[Triangle], z: float, center: tuple[float, float] = (0.0, 0.0)) -> dict:
    """Estimate radial envelope at a Z section by intersecting STL triangles.

    The function returns min/max/mean radii for all triangle-plane intersections.
    It is designed for axisymmetric CAD validation checks such as duct socket
    diameters and lead-in tapers.
    """
    points: list[tuple[float, float]] = []
    for tri in triangles:
        pts = list(tri)
        edges = ((pts[0], pts[1]), (pts[1], pts[2]), (pts[2], pts[0]))
        for a, b in edges:
            za = a[2] - z
            zb = b[2] - z
            if abs(za) < 1e-8 and abs(zb) < 1e-8:
                points.append((a[0], a[1]))
                points.append((b[0], b[1]))
            elif za == 0:
                points.append((a[0], a[1]))
            elif zb == 0:
                points.append((b[0], b[1]))
            elif (za < 0 < zb) or (zb < 0 < za):
                t = (z - a[2]) / (b[2] - a[2])
                x = a[0] + t * (b[0] - a[0])
                y = a[1] + t * (b[1] - a[1])
                points.append((x, y))

    if not points:
        return {"ok": False, "z": z, "point_count": 0, "error": "section has no STL intersections"}

    cx, cy = center
    radii = sorted(((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 for x, y in points)
    # Ignore tiny duplicate/interior artifacts by using a high percentile for
    # exterior radius and a low nonzero percentile for interior radius.
    exterior = _percentile(radii, 0.98)
    interior = _percentile([r for r in radii if r > 1e-6], 0.02)
    mean = sum(radii) / len(radii)
    return {
        "ok": True,
        "z": z,
        "point_count": len(points),
        "radius_min": min(radii),
        "radius_max": max(radii),
        "radius_mean": mean,
        "radius_outer_estimate": exterior,
        "radius_inner_estimate": interior,
        "diameter_outer_estimate": exterior * 2,
        "diameter_inner_estimate": interior * 2,
    }


def section_bbox_at_z(
    triangles: list[Triangle],
    z: float,
    region: tuple[tuple[float, float], tuple[float, float]] | None = None,
) -> dict:
    """Compute the XY bounding box of triangle-plane intersection points at Z.

    If `region` is given as ``((x_min, y_min), (x_max, y_max))``, also reports
    whether any intersection points fall inside that rectangle, enabling solid/void
    checks for non-circular features such as camera cutouts.
    """
    points: list[tuple[float, float]] = []
    for tri in triangles:
        pts = list(tri)
        edges = ((pts[0], pts[1]), (pts[1], pts[2]), (pts[2], pts[0]))
        for a, b in edges:
            za = a[2] - z
            zb = b[2] - z
            if abs(za) < 1e-8 and abs(zb) < 1e-8:
                points.append((a[0], a[1]))
                points.append((b[0], b[1]))
            elif za == 0:
                points.append((a[0], a[1]))
            elif zb == 0:
                points.append((b[0], b[1]))
            elif (za < 0 < zb) or (zb < 0 < za):
                t = (z - a[2]) / (b[2] - a[2])
                x = a[0] + t * (b[0] - a[0])
                y = a[1] + t * (b[1] - a[1])
                points.append((x, y))

    if not points:
        return {"ok": False, "z": z, "point_count": 0, "error": "section has no STL intersections"}

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    result: dict = {
        "ok": True,
        "z": z,
        "point_count": len(points),
        "bbox": {
            "x_min": min(xs), "x_max": max(xs),
            "y_min": min(ys), "y_max": max(ys),
        },
    }

    if region is not None:
        (rx0, ry0), (rx1, ry1) = region
        region_points = [(x, y) for x, y in points if rx0 <= x <= rx1 and ry0 <= y <= ry1]
        result["region"] = {"x_min": rx0, "y_min": ry0, "x_max": rx1, "y_max": ry1}
        result["region_point_count"] = len(region_points)
        result["region_has_points"] = len(region_points) > 0

    return result


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    q = max(0.0, min(1.0, q))
    index = q * (len(values) - 1)
    lo = int(index)
    hi = min(lo + 1, len(values) - 1)
    frac = index - lo
    return values[lo] * (1 - frac) + values[hi] * frac
