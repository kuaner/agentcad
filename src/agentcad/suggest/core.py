"""Suggest-checks command: recommend missing checks based on design.json.

``agentcad suggest-checks <model>`` reads the design contract and produces
conservative check templates for features that lack essential checks.

Output schema:
  {
    "ok": bool,
    "stage": "suggest-checks",
    "model": str,
    "suggestions": [{feature, missing, reason, template}],
    "design_found": bool
  }
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..contract.common import GEOMETRY_CHECK_TYPES, HOLE_CHECK_TYPES, ROOT_CHECK_TYPES, classify_feature
from ..contract.evidence import evaluate_design_intent_lint_dict, evaluate_feature_evidence_matrix_dict
from ..jsonio import read_json
from ..probe.planner import plan_probe_points
from ..workspace import model_dir, outputs_dir
from .templates import (
    _append_evidence_suggestions,
    _attachment_root_template,
    _first_check_template,
    _geometry_template,
    _hole_accessibility_template,
    _suggestion,
)
from .types import SuggestContext
from .quality import evaluate_suggestion_quality


def suggest_checks(project: Path, name: str) -> dict[str, Any]:
    """Analyze design.json and suggest missing checks."""
    mdir = model_dir(project, name)
    design = read_json(mdir / "design.json", default=None)

    if design is None or not isinstance(design, dict):
        return {
            "ok": False,
            "stage": "suggest-checks",
            "model": name,
            "suggestions": [],
            "suggestion_quality": evaluate_suggestion_quality([]),
            "design_found": False,
            "error": {"type": "DesignNotFound", "message": f"design.json not found for model '{name}'"},
        }

    features = design.get("features") or []
    checks = design.get("checks") or []
    params = read_json(mdir / "params.json", default={})
    metadata = read_json(mdir / "metadata.json", default={}) or {}
    out_dir = outputs_dir(project, name)
    geometry = read_json(out_dir / "geometry.json", default={}) or {}
    validation = read_json(out_dir / "validation.json", default={}) or {}
    observability = read_json(out_dir / "observability.json", default={}) or {}

    return suggest_from_contract(
        name,
        design,
        params=params if isinstance(params, dict) else {},
        metadata=metadata if isinstance(metadata, dict) else {},
        geometry=geometry if isinstance(geometry, dict) else {},
        validation=validation if isinstance(validation, dict) else {},
        observability=observability if isinstance(observability, dict) else {},
    )


def suggest_from_contract(
    name: str,
    design: dict[str, Any],
    *,
    params: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    geometry: dict[str, Any] | None = None,
    validation: dict[str, Any] | None = None,
    observability: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Suggest missing checks from in-memory contract artifacts."""
    params = params if isinstance(params, dict) else {}
    metadata = metadata if isinstance(metadata, dict) else {}
    geometry = geometry if isinstance(geometry, dict) else {}
    validation = validation if isinstance(validation, dict) else {}
    observability = observability if isinstance(observability, dict) else {}

    feature_evidence_matrix = evaluate_feature_evidence_matrix_dict(design)
    design_intent_lint = evaluate_design_intent_lint_dict(design)
    probe_plan = plan_probe_points(
        name,
        design,
        params=params,
        metadata=metadata,
        geometry=geometry,
        validation=validation,
        observability=observability,
        feature_evidence_matrix=feature_evidence_matrix,
    )
    ctx = SuggestContext(
        params=params,
        metadata=metadata,
        geometry=geometry,
        validation=validation,
        observability=observability,
        feature_evidence_matrix=feature_evidence_matrix,
        probe_plan=probe_plan,
    )
    features = design.get("features") or []
    checks = design.get("checks") or []

    # Build a map: check_id -> check_type
    check_type_map: dict[str, str] = {}
    check_map: dict[str, dict[str, Any]] = {}
    for c in checks:
        if isinstance(c, dict) and c.get("id") and c.get("type"):
            check_type_map[str(c["id"])] = str(c["type"])
            check_map[str(c["id"])] = c

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
        linked_checks = [
            check_map[cid] for cid in (str(cid) for cid in (feature.get("checks") or []))
            if cid in check_map
        ]
        feature_suggestion_missing: set[str] = set()

        # No checks at all.
        if not linked_types:
            suggestions.append(_suggestion(
                fid, "any_check",
                f"feature '{fid}' has no linked checks — add at least one geometry check",
                _first_check_template(fid, categories, ctx, feature=feature, linked_checks=linked_checks),
            ))
            feature_suggestion_missing.add("any_check")
        else:
            # No geometry checks.
            geom = linked_types & GEOMETRY_CHECK_TYPES
            if not geom:
                suggestions.append(_suggestion(
                    fid, "geometry_check",
                    f"feature '{fid}' has only non-geometry checks — add a section, diameter, or clearance check",
                    _geometry_template(fid, categories, ctx, feature=feature, linked_checks=linked_checks),
                ))
                feature_suggestion_missing.add("geometry_check")

            # Hole-specific: missing hole_accessibility.
            if "hole" in categories:
                hole_checks = linked_types & HOLE_CHECK_TYPES
                if "hole_accessibility" not in hole_checks and "hole_accessibility" not in linked_types:
                    suggestions.append(_suggestion(
                        fid, "hole_accessibility",
                        "hole-like feature has diameter/clearance checks but no tool envelope check",
                        _hole_accessibility_template(fid, ctx, feature=feature, linked_checks=linked_checks),
                    ))
                    feature_suggestion_missing.add("hole_accessibility")

            # Load-bearing attachment: missing root/interface check.
            if "load_bearing_attachment" in categories:
                root_checks = linked_types & ROOT_CHECK_TYPES
                if not root_checks:
                    suggestions.append(_suggestion(
                        fid, "root_interface_check",
                        "load-bearing feature has no root/interface check — detachment risk is unverified",
                        _attachment_root_template(fid, ctx, feature=feature, linked_checks=linked_checks),
                    ))
                    feature_suggestion_missing.add("root_interface_check")

        _append_evidence_suggestions(
            suggestions,
            feature=feature,
            categories=categories,
            linked_types=linked_types,
            linked_checks=linked_checks,
            ctx=ctx,
            existing_missing=feature_suggestion_missing,
        )

    suggestion_quality = evaluate_suggestion_quality(suggestions)
    return {
        "ok": True,
        "stage": "suggest-checks",
        "model": name,
        "suggestions": suggestions,
        "suggestion_quality": suggestion_quality,
        "feature_evidence_matrix": feature_evidence_matrix,
        "design_intent_lint": design_intent_lint,
        "probe_plan": probe_plan,
        "design_found": True,
    }
