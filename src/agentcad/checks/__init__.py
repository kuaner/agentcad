"""Check registry: typed dispatch for design-time and post-build checks.

Each check type lives in a topical module (``mesh``, ``section``,
``relations``) and registers itself via ``@register_check``.  Modules
that need to dispatch checks by ``type`` use :func:`run_check`; those
that only need to know which types are static (evaluable from
design.json alone) call :func:`static_types`.

Example
-------
.. code-block:: python

    from agentcad.checks import (
        CheckContext, run_check, static_types, known_types,
    )

    ctx = CheckContext(project=project, name=model, measure=measure_payload,
                       get_triangles=lazy_loader, out_dir=outputs_dir)
    result = run_check(check_dict, ctx)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

DESIGN_TIME = "design-time"
POST_BUILD = "post-build"


@dataclass
class CheckContext:
    """Bundle of per-validation state passed to every check evaluator.

    Attributes
    ----------
    project:
        Workspace root directory.
    name:
        Model name (the directory under ``models/``).
    measure:
        The measure-stage payload (mesh / bbox / volume facts).  Empty
        dict when the check is evaluated design-time without an STL.
    get_triangles:
        Lazy STL loader. Returns the parsed triangle list. Always
        callable, even when the STL has not yet been loaded; calling it
        triggers a one-time read.
    out_dir:
        ``models/<name>/outputs/`` — used for writing debug SVGs etc.
    """

    project: Path
    name: str
    measure: dict
    get_triangles: Callable[[], list]
    out_dir: Path


# Public registry. Mapping of check_type -> {"fn", "layer"}.
_CHECKS: dict[str, dict[str, Any]] = {}


def register_check(check_type: str, *, layer: str = POST_BUILD) -> Callable:
    """Register a check evaluator under ``check_type``.

    The wrapped function must have signature ``(check: dict, ctx:
    CheckContext) -> dict`` and return a payload with at least ``name``,
    ``type``, and ``ok`` keys.
    """

    def decorator(fn: Callable[[dict, CheckContext], dict]) -> Callable:
        if check_type in _CHECKS:
            raise RuntimeError(f"check type already registered: {check_type}")
        _CHECKS[check_type] = {"fn": fn, "layer": layer}
        return fn

    return decorator


def run_check(check: dict, ctx: CheckContext) -> dict:
    """Dispatch ``check`` to its registered evaluator.

    Returns an error payload with ``ok=False`` and a descriptive
    ``error`` field if the type is not registered.
    """
    check_type = str(check.get("type") or "")
    entry = _CHECKS.get(check_type)
    if entry is None:
        message = f"unsupported check type: {check_type}"
        return {
            "name": check.get("id") or check_type or "unknown",
            "type": check_type,
            "ok": False,
            "error": message,
            "error_detail": {"type": "UnsupportedCheckType", "message": message},
        }
    return entry["fn"](check, ctx)


def known_types() -> frozenset[str]:
    """All registered check types."""
    return frozenset(_CHECKS.keys())


def static_types() -> frozenset[str]:
    """Check types that can be evaluated without an STL (design-time)."""
    return frozenset(t for t, e in _CHECKS.items() if e["layer"] == DESIGN_TIME)


def post_build_types() -> frozenset[str]:
    """Check types that require an STL (or measure payload) to evaluate."""
    return frozenset(t for t, e in _CHECKS.items() if e["layer"] == POST_BUILD)


# Eager registration of all built-in check evaluators.  Importing the
# topical modules registers them as a side effect.
from . import mesh as _mesh  # noqa: E402,F401
from . import section as _section  # noqa: E402,F401
from . import relations as _relations  # noqa: E402,F401

__all__ = [
    "CheckContext",
    "DESIGN_TIME",
    "POST_BUILD",
    "register_check",
    "run_check",
    "known_types",
    "static_types",
    "post_build_types",
]
