from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import (
    ACCESS_CHECK_TYPES,
    DIMENSION_CHECK_TYPES,
    EVIDENCE_COLUMNS,
    FAILURE_MODE_REQUIRED_EVIDENCE,
    INTERFACE_RISK_CHECK_TYPES,
    POSITION_CHECK_TYPES,
    ROOT_WORDS,
    WALL_CHECK_TYPES,
    WALL_WORDS,
    _affects_for_failure,
    _feature_refs_for_intent,
    _iter_design_interfaces,
    _iter_failure_modes,
    _norm_key,
    _required_evidence_from_payload,
    classify_feature,
)
from .schema import load_design

def evaluate_feature_coverage(project: Path, name: str) -> list[dict]:
    _, design = load_design(project, name)
    return evaluate_feature_coverage_dict(design or {})


def evaluate_feature_coverage_dict(design: dict[str, Any]) -> list[dict]:
    features = design.get("features") or []
    checks = design.get("checks") or []
    check_ids = {str(c.get("id")) for c in checks if isinstance(c, dict) and c.get("id")}
    results: list[dict] = []
    for index, feature in enumerate(features):
        if not isinstance(feature, dict):
            results.append({
                "name": f"feature_coverage[{index}]",
                "type": "feature_coverage",
                "ok": False,
                "error": {"type": "FeatureShapeError", "message": "feature must be an object"},
            })
            continue
        feature_id = str(feature.get("id") or f"feature_{index}")
        linked = feature.get("checks") or []
        matched = [check_id for check_id in linked if str(check_id) in check_ids]
        results.append({
            "name": f"feature_coverage:{feature_id}",
            "type": "feature_coverage",
            "ok": bool(matched),
            "feature": feature_id,
            "checks": linked,
            "matchedChecks": matched,
        })
    return results


def evaluate_feature_evidence_matrix_dict(design: dict[str, Any]) -> list[dict]:
    """Return per-feature evidence coverage across mechanical risk dimensions.

    The matrix is a review aid and gate.  Every feature should prove where it is
    and how large it is.  Access, wall/root, and interface-risk evidence are
    required only when the feature text/classification makes that risk relevant.
    """
    features = design.get("features") or []
    checks = design.get("checks") or []
    check_map = {
        str(c.get("id")): c
        for c in checks
        if isinstance(c, dict) and c.get("id")
    }
    intent_requirements = _intent_evidence_requirements(design)
    rows: list[dict] = []
    for index, feature in enumerate(features):
        if not isinstance(feature, dict):
            rows.append({
                "feature": f"feature_{index}",
                "ok": False,
                "error": "feature must be an object",
                "missing": ["position", "dimensions"],
            })
            continue
        feature_id = str(feature.get("id") or f"feature_{index}")
        categories = classify_feature(feature)
        linked = _linked_check_defs(feature, check_map)
        required = _feature_evidence_requirements(feature, categories)
        intent_required = intent_requirements.get(feature_id, {})
        for key in EVIDENCE_COLUMNS:
            if intent_required.get(key):
                required[key] = True
        evidence = {
            "position": _evidence_cell(linked, POSITION_CHECK_TYPES, required["position"]),
            "dimensions": _evidence_cell(linked, DIMENSION_CHECK_TYPES, required["dimensions"]),
            "access": _evidence_cell(linked, ACCESS_CHECK_TYPES, required["access"]),
            "wall": _wall_evidence_cell(linked, required["wall"]),
            "interface_risk": _interface_evidence_cell(linked, required["interface_risk"], categories),
        }
        missing = [
            key for key, cell in evidence.items()
            if cell["required"] and not cell["ok"]
        ]
        rows.append({
            "feature": feature_id,
            "categories": sorted(categories) if categories else ["unclassified"],
            "required_evidence": [key for key in EVIDENCE_COLUMNS if required.get(key)],
            "requirement_reasons": intent_required.get("reasons", []),
            "linked_checks": [
                {"id": c.get("id"), "type": c.get("type")}
                for c in linked
            ],
            "evidence": evidence,
            "missing": missing,
            "ok": not missing,
        })
    return rows


def evaluate_design_intent_lint_dict(design: dict[str, Any]) -> list[dict]:
    """Return machine-readable design-intent coverage checks.

    Schema validation answers whether the fields are well shaped. Intent lint
    answers whether the declared surfaces, interfaces, and failure modes have
    measurable evidence attached to their affected features.
    """
    rows = evaluate_feature_evidence_matrix_dict(design)
    matrix = {str(row.get("feature")): row for row in rows}
    checks: list[dict] = []

    for index, surface in enumerate(design.get("functional_surfaces") or []):
        if not isinstance(surface, dict):
            continue
        fid = str(surface.get("feature_id") or "")
        row = matrix.get(fid)
        missing = _missing_from_row(row, {"position", "dimensions"})
        critical = bool(surface.get("critical", False))
        checks.append({
            "name": f"functional_surface:{surface.get('id') or index}",
            "type": "design_intent_lint",
            "ok": not missing,
            "severity": "blocking" if critical else "warning",
            "feature": fid,
            "missing": sorted(missing),
            "message": "functional surface needs position and dimension evidence",
        })

    for index, interface in enumerate(_iter_design_interfaces(design)):
        if not isinstance(interface, dict):
            continue
        required = _interface_required_evidence(interface)
        refs = _feature_refs_for_intent(interface)
        per_feature = []
        ok = True
        for fid in refs:
            missing = _missing_from_row(matrix.get(fid), required)
            if missing:
                ok = False
            per_feature.append({"feature": fid, "missing": sorted(missing)})
        checks.append({
            "name": f"interface:{interface.get('id') or index}",
            "type": "design_intent_lint",
            "ok": ok,
            "severity": "blocking",
            "interface_type": interface.get("type"),
            "required_evidence": sorted(required),
            "features": per_feature,
            "message": "interface needs measurable evidence for fit, access, and assembly risk",
        })

    for index, failure in enumerate(_iter_failure_modes(design)):
        if not isinstance(failure, dict):
            continue
        required = _failure_mode_required_evidence(failure)
        severity = str(failure.get("severity", "medium")).lower()
        blocking = severity in {"high", "blocking", "critical"}
        per_feature = []
        ok = True
        for fid in _affects_for_failure(failure):
            missing = _missing_from_row(matrix.get(fid), required)
            if missing:
                ok = False
            per_feature.append({"feature": fid, "missing": sorted(missing)})
        checks.append({
            "name": f"failure_mode:{failure.get('id') or index}",
            "type": "design_intent_lint",
            "ok": ok,
            "severity": "blocking" if blocking else "warning",
            "mode": failure.get("mode"),
            "required_evidence": sorted(required),
            "features": per_feature,
            "message": "declared failure mode needs matching evidence before delivery",
        })

    return checks


def _linked_check_defs(feature: dict[str, Any], check_map: dict[str, dict]) -> list[dict]:
    linked: list[dict] = []
    for check_id in feature.get("checks") or []:
        check = check_map.get(str(check_id))
        if isinstance(check, dict):
            linked.append(check)
    return linked


def _feature_evidence_requirements(feature: dict[str, Any], categories: set[str]) -> dict[str, bool]:
    text = " ".join(str(feature.get(k, "")) for k in ("id", "intent", "description")).lower()
    wall_risk = "load_bearing_attachment" in categories or any(word in text for word in WALL_WORDS)
    interface_risk = "interface" in categories or "hole" in categories
    access_risk = "hole" in categories
    return {
        "position": True,
        "dimensions": True,
        "access": access_risk,
        "wall": wall_risk,
        "interface_risk": interface_risk,
    }


def _intent_evidence_requirements(design: dict[str, Any]) -> dict[str, dict[str, Any]]:
    requirements: dict[str, dict[str, Any]] = {}

    def require(fid: str, columns: set[str] | frozenset[str], reason: dict[str, Any]) -> None:
        if not fid:
            return
        row = requirements.setdefault(fid, {key: False for key in EVIDENCE_COLUMNS})
        row.setdefault("reasons", [])
        for column in columns:
            if column in EVIDENCE_COLUMNS:
                row[column] = True
        row["reasons"].append(reason)

    for surface in design.get("functional_surfaces") or []:
        if not isinstance(surface, dict):
            continue
        columns = {"position", "dimensions"} if surface.get("critical", True) else {"position"}
        require(str(surface.get("feature_id") or ""), columns, {
            "source": "functional_surface",
            "id": surface.get("id"),
            "role": surface.get("role"),
        })

    for interface in _iter_design_interfaces(design):
        if not isinstance(interface, dict):
            continue
        columns = _interface_required_evidence(interface)
        for fid in _feature_refs_for_intent(interface):
            require(fid, columns, {
                "source": "interface",
                "id": interface.get("id"),
                "type": interface.get("type"),
            })

    for failure in _iter_failure_modes(design):
        if not isinstance(failure, dict):
            continue
        columns = _failure_mode_required_evidence(failure)
        for fid in _affects_for_failure(failure):
            require(fid, columns, {
                "source": "failure_mode",
                "id": failure.get("id"),
                "mode": failure.get("mode"),
                "severity": failure.get("severity", "medium"),
            })

    return requirements


def _interface_required_evidence(interface: dict[str, Any]) -> frozenset[str]:
    text = " ".join(
        str(interface.get(k, ""))
        for k in ("id", "type", "role", "intent", "description")
    ).lower()
    required: set[str] = {"position", "dimensions"}
    if any(word in text for word in ("fastener", "screw", "bolt", "hole", "bore", "tool")):
        required.update({"access", "interface_risk"})
    if any(word in text for word in ("mate", "interface", "socket", "pin", "dovetail", "snap", "gear", "fit")):
        required.add("interface_risk")
    if interface.get("clearance_mm") is not None or "clearance" in text:
        required.add("interface_risk")
    if interface.get("access_axis") is not None or interface.get("insertion_axis") is not None:
        required.add("access")
    for mode in interface.get("failure_modes") or []:
        if isinstance(mode, str):
            required.update(FAILURE_MODE_REQUIRED_EVIDENCE.get(_norm_key(mode), frozenset()))
    return frozenset(required)


def _failure_mode_required_evidence(failure: dict[str, Any]) -> frozenset[str]:
    explicit = _required_evidence_from_payload(failure)
    if explicit:
        return frozenset(explicit)
    mode = _norm_key(failure.get("mode"))
    return FAILURE_MODE_REQUIRED_EVIDENCE.get(mode, frozenset({"position", "dimensions"}))

def _missing_from_row(row: dict | None, required: set[str] | frozenset[str]) -> set[str]:
    if not row:
        return set(required)
    evidence = row.get("evidence") or {}
    missing = set()
    for key in required:
        cell = evidence.get(key) or {}
        if not cell.get("ok"):
            missing.add(key)
    return missing

def _evidence_cell(checks: list[dict], accepted_types: frozenset[str], required: bool) -> dict:
    matched = [
        str(check.get("id"))
        for check in checks
        if str(check.get("type", "")) in accepted_types and check.get("id")
    ]
    return {
        "required": required,
        "ok": (not required) or bool(matched),
        "checks": matched,
        "accepted_types": sorted(accepted_types),
    }


def _wall_evidence_cell(checks: list[dict], required: bool) -> dict:
    matched: list[str] = []
    for check in checks:
        check_type = str(check.get("type", ""))
        check_id = str(check.get("id", ""))
        if check_type in WALL_CHECK_TYPES:
            matched.append(check_id)
        elif check_type in ("section_bbox_at_z", "feature_position") and _text_has_any(check_id, ROOT_WORDS):
            matched.append(check_id)
    return {
        "required": required,
        "ok": (not required) or bool(matched),
        "checks": matched,
        "accepted_types": sorted(WALL_CHECK_TYPES | {"section_bbox_at_z", "feature_position"}),
    }


def _interface_evidence_cell(checks: list[dict], required: bool, categories: set[str]) -> dict:
    matched: list[str] = []
    for check in checks:
        check_type = str(check.get("type", ""))
        check_id = str(check.get("id", ""))
        if "hole" in categories:
            if check_type == "min_clearance":
                matched.append(check_id)
        elif check_type in INTERFACE_RISK_CHECK_TYPES:
            matched.append(check_id)
    return {
        "required": required,
        "ok": (not required) or bool(matched),
        "checks": matched,
        "accepted_types": sorted(INTERFACE_RISK_CHECK_TYPES),
    }


def _text_has_any(text: str, words: frozenset[str]) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in words)
