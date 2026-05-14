from __future__ import annotations

from typing import Any


def _region(value: Any) -> tuple[tuple[float, float], tuple[float, float]] | None:
    if not isinstance(value, list) or len(value) != 2:
        return None
    first = _pair(value[0])
    second = _pair(value[1])
    if first is None or second is None:
        return None
    return first, second


def _pair(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    a = _num(value[0])
    b = _num(value[1])
    if a is None or b is None:
        return None
    return a, b


def _triple(value: Any) -> tuple[float, float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    a = _num(value[0])
    b = _num(value[1])
    c = _num(value[2])
    if a is None or b is None or c is None:
        return None
    return a, b, c


def _mid_pair(value: Any) -> float:
    pair = _pair(value)
    if pair is None:
        return 0.0
    return (pair[0] + pair[1]) / 2.0


def _num(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _region_arg(region: tuple[tuple[float, float], tuple[float, float]]) -> str:
    return ",".join(_fmt(v) for v in (region[0][0], region[0][1], region[1][0], region[1][1]))


def _fmt(value: float) -> str:
    return f"{float(value):.4f}".rstrip("0").rstrip(".")


def _norm(value: Any) -> str:
    return "".join(ch for ch in str(value).lower() if ch.isalnum())
