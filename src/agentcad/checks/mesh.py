"""Mesh-level checks: bbox_size, watertight, min_triangles, volume_range,
artifact_exists, metadata_equals.

These checks operate on the measure-stage payload (or filesystem state
for ``artifact_exists`` and ``metadata_equals``) and never need to read
the STL directly.
"""
from __future__ import annotations

from typing import Any

from ..jsonio import read_json
from ..workspace import model_dir
from . import CheckContext, POST_BUILD, register_check


def _vec_close(actual: Any, expected: Any, tolerance: float) -> bool:
    if (
        not isinstance(actual, list)
        or not isinstance(expected, list)
        or len(actual) != len(expected)
    ):
        return False
    return all(abs(float(a) - float(e)) <= tolerance for a, e in zip(actual, expected))


def _get_path(payload: Any, path_expr: str) -> Any:
    current = payload
    for segment in path_expr.split("."):
        if not segment:
            continue
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        else:
            return None
    return current


@register_check("bbox_size", layer=POST_BUILD)
def evaluate_bbox_size(check: dict, ctx: CheckContext) -> dict:
    geometry = ctx.measure.get("geometry") or {}
    expected = check.get("expected")
    tolerance = float(check.get("tolerance", 0.0))
    actual = (geometry.get("bbox") or {}).get("size")
    return {
        "name": check.get("id") or "bbox_size",
        "type": "bbox_size",
        "ok": _vec_close(actual, expected, tolerance),
        "expected": expected,
        "actual": actual,
        "tolerance": tolerance,
    }


@register_check("watertight", layer=POST_BUILD)
def evaluate_watertight(check: dict, ctx: CheckContext) -> dict:
    geometry = ctx.measure.get("geometry") or {}
    expected = bool(check.get("expected", True))
    actual = bool((geometry.get("mesh") or {}).get("watertight"))
    return {
        "name": check.get("id") or "watertight",
        "type": "watertight",
        "ok": actual == expected,
        "expected": expected,
        "actual": actual,
    }


@register_check("min_triangles", layer=POST_BUILD)
def evaluate_min_triangles(check: dict, ctx: CheckContext) -> dict:
    geometry = ctx.measure.get("geometry") or {}
    expected = int(check.get("expected", 0))
    actual = int((geometry.get("mesh") or {}).get("triangles") or 0)
    return {
        "name": check.get("id") or "min_triangles",
        "type": "min_triangles",
        "ok": actual >= expected,
        "expected": expected,
        "actual": actual,
    }


@register_check("volume_range", layer=POST_BUILD)
def evaluate_volume_range(check: dict, ctx: CheckContext) -> dict:
    geometry = ctx.measure.get("geometry") or {}
    actual = float((geometry.get("mass_properties") or {}).get("volume") or 0.0)
    minimum = check.get("min")
    maximum = check.get("max")
    ok = True
    if minimum is not None:
        ok = ok and actual >= float(minimum)
    if maximum is not None:
        ok = ok and actual <= float(maximum)
    return {
        "name": check.get("id") or "volume_range",
        "type": "volume_range",
        "ok": ok,
        "actual": actual,
        "min": minimum,
        "max": maximum,
    }


@register_check("artifact_exists", layer=POST_BUILD)
def evaluate_artifact_exists(check: dict, ctx: CheckContext) -> dict:
    raw_path = str(check.get("path") or "")
    path = model_dir(ctx.project, ctx.name) / raw_path
    return {
        "name": check.get("id") or f"artifact_exists:{raw_path}",
        "type": "artifact_exists",
        "ok": path.exists(),
        "path": str(path),
    }


@register_check("metadata_equals", layer=POST_BUILD)
def evaluate_metadata_equals(check: dict, ctx: CheckContext) -> dict:
    metadata_path = model_dir(ctx.project, ctx.name) / "metadata.json"
    metadata = read_json(metadata_path, default={}) or {}
    path_expr = str(check.get("path") or "")
    expected = check.get("expected")
    actual = _get_path(metadata, path_expr)
    return {
        "name": check.get("id") or f"metadata_equals:{path_expr}",
        "type": "metadata_equals",
        "ok": actual == expected,
        "path": path_expr,
        "expected": expected,
        "actual": actual,
        "source": str(metadata_path),
    }
