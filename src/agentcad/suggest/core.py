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

from ..contract.common import GEOMETRY_CHECK_TYPES, HOLE_CHECK_TYPES, ROOT_CHECK_TYPES, ROOT_WORDS, classify_feature
from ..contract.evidence import evaluate_design_intent_lint_dict, evaluate_feature_evidence_matrix_dict
from ..jsonio import read_json
from ..probe.planner import plan_probe_points
from ..workspace import format_model_target, model_dir, outputs_dir_for_variant, parse_model_target, variant_params_path
from .patches import apply_suggestion_patches, build_suggestion_patches
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


def suggest_checks(project: Path, name: str, *, apply: bool = False) -> dict[str, Any]:
    """Analyze design.json and suggest missing checks."""
    model_name, variant = parse_model_target(name)
    target = format_model_target(model_name, variant)
    mdir = model_dir(project, model_name)
    design_path = mdir / "design.json"
    design = read_json(design_path, default=None)

    if design is None or not isinstance(design, dict):
        return {
            "ok": False,
            "stage": "suggest-checks",
            "model": model_name,
            "variant": variant,
            "suggestions": [],
            "patches": [],
            "suggestion_quality": evaluate_suggestion_quality([]),
            "design_found": False,
            "error": {"type": "DesignNotFound", "message": f"design.json not found for model '{model_name}'"},
        }

    params_path = variant_params_path(project, model_name, variant) if variant else mdir / "params.json"
    params = read_json(params_path, default={})
    out_dir = outputs_dir_for_variant(project, model_name, variant)
    metadata = read_json(out_dir / "metadata.json", default=None)
    if metadata is None:
        metadata = read_json(mdir / "metadata.json", default={}) or {}
    geometry = read_json(out_dir / "geometry.json", default={}) or {}
    validation = read_json(out_dir / "validation.json", default={}) or {}
    observability = read_json(out_dir / "observability.json", default={}) or {}

    result = suggest_from_contract(
        target,
        design,
        params=params if isinstance(params, dict) else {},
        metadata=metadata if isinstance(metadata, dict) else {},
        geometry=geometry if isinstance(geometry, dict) else {},
        validation=validation if isinstance(validation, dict) else {},
        observability=observability if isinstance(observability, dict) else {},
    )
    result["model"] = model_name
    result["variant"] = variant
    result["target"] = target
    if apply:
        if variant:
            result["ok"] = False
            result["error"] = {"type": "VariantApplyNotAllowed", "message": "suggest-checks --apply cannot modify shared design.json through a variant target"}
            return result
        quality = result.get("suggestion_quality") or {}
        if int(quality.get("placeholder_count") or 0) > 0:
            result["ok"] = False
            result["error"] = {"type": "UnresolvedPlaceholders", "message": "refusing to apply suggested checks with unresolved <...> placeholders"}
            return result
        updated = apply_suggestion_patches(design, result.get("patches") or [], design_path)
        result["applied"] = True
        result["applied_patch_count"] = len(result.get("patches") or [])
        result["applied_check_count"] = len(updated.get("checks") or []) - len(design.get("checks") or [])
        result["artifacts"] = {"design": str(design_path)}
    return result


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
                if not _has_root_interface_check(linked_checks):
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
    patches = build_suggestion_patches(design, suggestions)
    return {
        "ok": True,
        "stage": "suggest-checks",
        "model": name,
        "suggestions": suggestions,
        "patches": patches,
        "suggestion_quality": suggestion_quality,
        "feature_evidence_matrix": feature_evidence_matrix,
        "design_intent_lint": design_intent_lint,
        "probe_plan": probe_plan,
        "design_found": True,
    }


def _has_root_interface_check(linked_checks: list[dict[str, Any]]) -> bool:
    for check in linked_checks:
        check_type = str(check.get("type", ""))
        check_id = str(check.get("id", ""))
        if check_type in ROOT_CHECK_TYPES:
            return True
        if check_type == "section_bbox_at_z" and _text_has_any(check_id, ROOT_WORDS):
            return True
    return False


def _text_has_any(text: str, words: frozenset[str]) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in words)
