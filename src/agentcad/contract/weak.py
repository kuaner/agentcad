from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import GEOMETRY_CHECK_TYPES, HOLE_CHECK_TYPES, ROOT_CHECK_TYPES, ROOT_WORDS, classify_feature
from .schema import load_design

def evaluate_weak_check_warnings(project: Path, name: str) -> list[dict]:
    _, design = load_design(project, name)
    return evaluate_weak_check_warnings_dict(design or {})


def evaluate_weak_check_warnings_dict(design: dict[str, Any]) -> list[dict]:
    features = design.get("features") or []
    checks = design.get("checks") or []
    check_type_map = {
        str(c.get("id")): str(c.get("type", ""))
        for c in checks
        if isinstance(c, dict) and c.get("id")
    }
    warnings: list[dict] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        feature_id = str(feature.get("id") or "unknown")
        categories = classify_feature(feature)
        linked_ids = [str(cid) for cid in (feature.get("checks") or [])]

        if not linked_ids:
            warnings.append({
                "feature": feature_id,
                "category": sorted(categories) if categories else ["unclassified"],
                "severity": "blocking",
                "missing": "any_check",
                "message": f"feature '{feature_id}' has no checks linked — add at least one geometry check",
                "hint": "Link outer_diameter_at_z, inner_diameter_at_z, section_bbox_at_z, or min_clearance",
            })
            continue

        linked_types = {check_type_map.get(cid, "") for cid in linked_ids}
        geometry_checks = linked_types & GEOMETRY_CHECK_TYPES
        if not geometry_checks:
            warnings.append({
                "feature": feature_id,
                "category": sorted(categories) if categories else ["unclassified"],
                "severity": "blocking",
                "missing": "geometry_check",
                "linkedCheckTypes": sorted(t for t in linked_types if t),
                "message": f"feature '{feature_id}' has no geometry checks — geometry is not verified",
                "hint": "Use agentcad probe/inspect and add section/diameter/clearance checks",
            })
            continue

        # Category-specific gaps.
        if "hole" in categories:
            hole_checks = linked_types & HOLE_CHECK_TYPES
            if "hole_accessibility" not in hole_checks:
                warnings.append({
                    "feature": feature_id,
                    "category": ["hole"],
                    "severity": "blocking",
                    "missing": "hole_accessibility",
                    "message": f"hole-like feature '{feature_id}' has diameter/clearance checks but no access-envelope check",
                    "hint": "Add hole_accessibility check for the tool/bolt approach direction",
                })

        if "load_bearing_attachment" in categories:
            if not _has_root_interface_check(linked_ids, check_type_map):
                warnings.append({
                    "feature": feature_id,
                    "category": ["load_bearing_attachment"],
                    "severity": "warning",
                    "missing": "root_interface_check",
                    "message": f"load-bearing feature '{feature_id}' has no root/interface check — detachment risk is unverified",
                    "hint": "Add min_wall_thickness at the feature root, or min_clearance at the attachment interface",
                })

    return warnings


def _has_root_interface_check(linked_ids: list[str], check_type_map: dict[str, str]) -> bool:
    for check_id in linked_ids:
        check_type = check_type_map.get(check_id, "")
        if check_type in ROOT_CHECK_TYPES:
            return True
        if check_type == "section_bbox_at_z" and _text_has_any(check_id, ROOT_WORDS):
            return True
    return False


def _text_has_any(text: str, words: frozenset[str]) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in words)
