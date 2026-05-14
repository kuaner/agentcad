from __future__ import annotations

import math

from typing import Any

from ..stl import Triangle, Vec3, normalize
from .types import AssemblyError, Transform


def _parse_transform(raw: dict, cid: str) -> Transform:
    if not isinstance(raw, dict):
        raise AssemblyError("TransformInvalid", f"component {cid} transform must be an object")
    if "scale" in raw:
        raise AssemblyError("ScaleNotAllowed", f"component {cid} transform scale is not allowed")
    allowed = {"translation", "rotation_euler_deg"}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise AssemblyError("TransformFieldInvalid", f"component {cid} transform has unsupported fields: {', '.join(unknown)}")

    translation = _vec3(raw.get("translation", [0, 0, 0]), f"{cid}.transform.translation")
    rotation_euler_deg = _vec3(raw.get("rotation_euler_deg", [0, 0, 0]), f"{cid}.transform.rotation_euler_deg")
    rotation = _rotation_matrix_xyz(rotation_euler_deg)
    matrix = [
        [rotation[0][0], rotation[0][1], rotation[0][2], translation[0]],
        [rotation[1][0], rotation[1][1], rotation[1][2], translation[1]],
        [rotation[2][0], rotation[2][1], rotation[2][2], translation[2]],
        [0.0, 0.0, 0.0, 1.0],
    ]
    return Transform(translation=translation, rotation_euler_deg=rotation_euler_deg, rotation=rotation, matrix=matrix)


def _vec3(value: Any, label: str) -> Vec3:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise AssemblyError("VectorInvalid", f"{label} must be a 3-item number array")
    try:
        return (float(value[0]), float(value[1]), float(value[2]))
    except (TypeError, ValueError) as exc:
        raise AssemblyError("VectorInvalid", f"{label} must contain numbers") from exc


def _rotation_matrix_xyz(euler_deg: Vec3) -> tuple[Vec3, Vec3, Vec3]:
    rx, ry, rz = [math.radians(v) for v in euler_deg]
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    mx: tuple[Vec3, Vec3, Vec3] = ((1.0, 0.0, 0.0), (0.0, cx, -sx), (0.0, sx, cx))
    my: tuple[Vec3, Vec3, Vec3] = ((cy, 0.0, sy), (0.0, 1.0, 0.0), (-sy, 0.0, cy))
    mz: tuple[Vec3, Vec3, Vec3] = ((cz, -sz, 0.0), (sz, cz, 0.0), (0.0, 0.0, 1.0))
    return _matmul3(_matmul3(mz, my), mx)


def _matmul3(a: tuple[Vec3, Vec3, Vec3], b: tuple[Vec3, Vec3, Vec3]) -> tuple[Vec3, Vec3, Vec3]:
    rows = []
    for i in range(3):
        rows.append(
            (
                a[i][0] * b[0][0] + a[i][1] * b[1][0] + a[i][2] * b[2][0],
                a[i][0] * b[0][1] + a[i][1] * b[1][1] + a[i][2] * b[2][1],
                a[i][0] * b[0][2] + a[i][1] * b[1][2] + a[i][2] * b[2][2],
            )
        )
    return (rows[0], rows[1], rows[2])


def _transform_point(point: Vec3, transform: Transform) -> Vec3:
    return _transform_point_matrix(point, transform.matrix)


def _transform_vector(vector: Vec3, transform: Transform) -> Vec3:
    return normalize(
        (
            transform.rotation[0][0] * vector[0] + transform.rotation[0][1] * vector[1] + transform.rotation[0][2] * vector[2],
            transform.rotation[1][0] * vector[0] + transform.rotation[1][1] * vector[1] + transform.rotation[1][2] * vector[2],
            transform.rotation[2][0] * vector[0] + transform.rotation[2][1] * vector[1] + transform.rotation[2][2] * vector[2],
        )
    )


def _transform_point_matrix(point: Vec3, matrix: list[list[float]]) -> Vec3:
    return (
        matrix[0][0] * point[0] + matrix[0][1] * point[1] + matrix[0][2] * point[2] + matrix[0][3],
        matrix[1][0] * point[0] + matrix[1][1] * point[1] + matrix[1][2] * point[2] + matrix[1][3],
        matrix[2][0] * point[0] + matrix[2][1] * point[1] + matrix[2][2] * point[2] + matrix[2][3],
    )


def _transform_triangle(tri: Triangle, transform: Transform) -> Triangle:
    return (_transform_point(tri[0], transform), _transform_point(tri[1], transform), _transform_point(tri[2], transform))


def _translate_triangle(tri: Triangle, offset: Vec3) -> Triangle:
    return (_add(tri[0], offset), _add(tri[1], offset), _add(tri[2], offset))


def _add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(v: Vec3, scalar: float) -> Vec3:
    return (v[0] * scalar, v[1] * scalar, v[2] * scalar)


def _round_vec(value: Any, digits: int = 6) -> list[float]:
    return [round(float(value[0]), digits), round(float(value[1]), digits), round(float(value[2]), digits)]


def _round_matrix(value: list[list[float]], digits: int = 6) -> list[list[float]]:
    return [[round(float(item), digits) for item in row] for row in value]
