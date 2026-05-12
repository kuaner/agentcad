"""Suggest-checks command: recommend missing checks based on design.json.

``agentcad suggest-checks <model>`` reads the design contract and produces
conservative check templates for features that lack essential checks.

Output schema:
  {
    "ok": bool,
    "stage": "suggest_checks",
    "model": str,
    "suggestions": [{feature, missing, reason, template}],
    "design_found": bool
  }
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .contract import (
    classify_feature,
    HOLE_CHECK_TYPES,
    HOLE_WORDS,
    ATTACHMENT_WORDS,
    INTERFACE_WORDS,
    ROOT_CHECK_TYPES,
    GEOMETRY_CHECK_TYPES,
)
from .jsonio import read_json
from .workspace import model_dir


def suggest_checks(project: Path, name: str) -> dict[str, Any]:
    """Analyze design.json and suggest missing checks."""
    mdir = model_dir(project, name)
    design = read_json(mdir / "design.json", default=None)

    if design is None or not isinstance(design, dict):
        return {
            "ok": False,
            "stage": "suggest_checks",
            "model": name,
            "suggestions": [],
            "design_found": False,
            "error": {"type": "DesignNotFound", "message": f"design.json not found for model '{name}'"},
        }

    features = design.get("features") or []
    checks = design.get("checks") or []
    params = read_json(mdir / "params.json", default={})

    # Build a map: check_id -> check_type
    check_type_map: dict[str, str] = {}
    for c in checks:
        if isinstance(c, dict) and c.get("id") and c.get("type"):
            check_type_map[str(c["id"])] = str(c["type"])

    # Build a map: feature_id -> set of linked check types
    feature_check_types: dict[str, set[str]] = {}
    for feature in features:
        if not isinstance(feature, dict) or not feature.get("id"):
            continue
        fid = str(feature["id"])
        linked_ids = [str(cid) for cid in (feature.get("checks") or [])]
        feature_check_types[fid] = {check_type_map.get(cid, "") for cid in linked_ids if cid in check_type_map}

    suggestions: list[dict[str, Any]] = []

    for feature in features:
        if not isinstance(feature, dict) or not feature.get("id"):
            continue
        fid = str(feature["id"])
        categories = classify_feature(feature)
        linked_types = feature_check_types.get(fid, set())

        # No checks at all.
        if not linked_types:
            suggestions.append(_suggestion(
                fid, "any_check",
                f"feature '{fid}' has no linked checks — add at least one geometry check",
                _first_check_template(fid, categories, params),
            ))
            continue

        # No geometry checks.
        geom = linked_types & GEOMETRY_CHECK_TYPES
        if not geom:
            suggestions.append(_suggestion(
                fid, "geometry_check",
                f"feature '{fid}' has only non-geometry checks — add a section, diameter, or clearance check",
                _geometry_template(fid, categories),
            ))
            continue

        # Hole-specific: missing hole_accessibility.
        if "hole" in categories:
            hole_checks = linked_types & HOLE_CHECK_TYPES
            if "hole_accessibility" not in hole_checks and "hole_accessibility" not in linked_types:
                suggestions.append(_suggestion(
                    fid, "hole_accessibility",
                    "hole-like feature has diameter/clearance checks but no tool envelope check",
                    _hole_accessibility_template(fid, params),
                ))

        # Load-bearing attachment: missing root/interface check.
        if "load_bearing_attachment" in categories:
            root_checks = linked_types & ROOT_CHECK_TYPES
            if not root_checks:
                suggestions.append(_suggestion(
                    fid, "root_interface_check",
                    "load-bearing feature has no root/interface check — detachment risk is unverified",
                    _attachment_root_template(fid, params),
                ))

    return {
        "ok": True,
        "stage": "suggest_checks",
        "model": name,
        "suggestions": suggestions,
        "design_found": True,
    }


def _suggestion(feature: str, missing: str, reason: str, template: dict) -> dict[str, Any]:
    return {
        "feature": feature,
        "missing": missing,
        "reason": reason,
        "template": template,
    }


# ── Template generators ────────────────────────────────────────────────────


def _first_check_template(fid: str, categories: set[str], params: dict) -> dict:
    """Generate a starter check template based on feature classification."""
    if "hole" in categories:
        return _hole_accessibility_template(fid, params)
    if "load_bearing_attachment" in categories:
        return _attachment_root_template(fid, params)
    if "interface" in categories:
        return _interface_template(fid)
    return {
        "id": f"{fid}_bbox",
        "type": "bbox_size",
        "expected": ["<width>", "<depth>", "<height>"],
        "tolerance": "<tolerance>",
    }


def _geometry_template(fid: str, categories: set[str]) -> dict:
    """Template for a first geometry check when only non-geometry checks exist."""
    if "hole" in categories:
        return {
            "id": f"{fid}_diameter",
            "type": "inner_diameter_at_z",
            "z": "<z>",
            "expected": "<diameter>",
            "tolerance": "<tolerance>",
            "center": ["<x>", "<y>"],
        }
    return {
        "id": f"{fid}_section",
        "type": "section_bbox_at_z",
        "z": "<z>",
        "expected": ["<width>", "<depth>"],
        "tolerance": "<tolerance>",
        "center": ["<x>", "<y>"],
    }


def _hole_accessibility_template(fid: str, params: dict) -> dict:
    """Template for hole_accessibility check."""
    # Try to infer hole diameter from params.
    diameter_hint = _find_param_hint(params, HOLE_WORDS | {"diameter", "dia", "d", "radius", "r"})
    clearance_hint = _find_param_hint(params, {"clearance", "tool", "fastener", "screw", "bolt"})
    return {
        "id": f"{fid}_access",
        "type": "hole_accessibility",
        "axis": "<z|x|y>",
        "center": ["<x>", "<y>"],
        "hole_diameter": diameter_hint or "<diameter>",
        "clearance_diameter": clearance_hint or "<tool_diameter>",
        "approach": "top",
    }


def _attachment_root_template(fid: str, params: dict) -> dict:
    """Template for min_wall_thickness or min_clearance at attachment root."""
    wall_hint = _find_param_hint(params, {"wall", "thickness", "rib", "boss", "tab", "lip"})
    if wall_hint:
        return {
            "id": f"{fid}_wall",
            "type": "min_wall_thickness",
            "axis": "<z|x|y>",
            "region": [["<x0>", "<y0>"], ["<x1>", "<y1>"]],
            "min_mm": wall_hint,
        }
    return {
        "id": f"{fid}_clearance",
        "type": "min_clearance",
        "feature_a": {"type": "<shape_type>", "<descriptor_fields>": "<values>"},
        "feature_b": {"type": "<shape_type>", "<descriptor_fields>": "<values>"},
        "min_mm": "<min_clearance>",
    }


def _interface_template(fid: str) -> dict:
    """Template for interface features: min_clearance between mating parts."""
    return {
        "id": f"{fid}_clearance",
        "type": "min_clearance",
        "feature_a": {"type": "<shape_type>", "<descriptor_fields>": "<values>"},
        "feature_b": {"type": "<shape_type>", "<descriptor_fields>": "<values>"},
        "min_mm": "<min_clearance>",
    }


def _find_param_hint(params: dict, keywords: frozenset | set) -> str | None:
    """Search params.json for keys matching keywords and return first numeric value.

    Iterates in dict insertion order (not sorted) to prefer keys that appear
    earlier in the user's params.json, which typically lists primary dimensions
    before derived ones like clearance.
    """
    if not isinstance(params, dict):
        return None
    for key, value in params.items():
        key_lower = str(key).lower()
        if any(kw in key_lower for kw in keywords) and isinstance(value, (int, float)):
            return str(value)
    return None