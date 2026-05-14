from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Check types that verify actual geometric shape behavior (not only global mesh).
GEOMETRY_CHECK_TYPES = frozenset({
    "outer_diameter_at_z",
    "inner_diameter_at_z",
    "diameter_decreases_along_z",
    "section_bbox_at_z",
    "section_component_count",
    "min_clearance",
    "hole_accessibility",
    "min_wall_thickness",
    "feature_position",
})

# Feature classification keywords.
HOLE_WORDS = frozenset({"hole", "bore", "screw", "bolt", "fastener", "counterbore", "countersink"})
ATTACHMENT_WORDS = frozenset({"rib", "boss", "tab", "lip", "arm", "flange", "hook", "hinge"})
INTERFACE_WORDS = frozenset({"socket", "pin", "dovetail", "gear", "mate", "interface", "neck"})

# Check types that verify hole-specific behavior.
HOLE_CHECK_TYPES = frozenset({"hole_accessibility", "inner_diameter_at_z", "min_clearance"})
# Check types that verify attachment root/interface behavior.
ROOT_CHECK_TYPES = frozenset({"min_wall_thickness", "min_clearance", "feature_position"})

# Evidence dimensions used by review / suggest-checks.  These are deliberately
# coarse: the goal is to catch unmeasured mechanical facts without forcing every
# feature into a heavyweight schema.
POSITION_CHECK_TYPES = frozenset({
    "feature_position",
    "section_bbox_at_z",
    "section_component_count",
    "inner_diameter_at_z",
    "outer_diameter_at_z",
    "min_clearance",
    "hole_accessibility",
})
DIMENSION_CHECK_TYPES = frozenset({
    "bbox_size",
    "inner_diameter_at_z",
    "outer_diameter_at_z",
    "diameter_decreases_along_z",
    "section_bbox_at_z",
    "min_wall_thickness",
    "min_clearance",
})
ACCESS_CHECK_TYPES = frozenset({"hole_accessibility"})
WALL_CHECK_TYPES = frozenset({"min_wall_thickness", "min_clearance"})
INTERFACE_RISK_CHECK_TYPES = frozenset({"min_clearance", "metadata_equals", "hole_accessibility"})

WALL_WORDS = frozenset({"wall", "shell", "thin", "sleeve", "tube", "web", "skin", "rim"})
ROOT_WORDS = frozenset({"root", "base", "interface", "junction", "connected", "attach", "attachment"})
EVIDENCE_COLUMNS = ("position", "dimensions", "access", "wall", "interface_risk")
SEVERITIES = frozenset({"info", "low", "medium", "warning", "high", "blocking", "critical"})

FAILURE_MODE_REQUIRED_EVIDENCE = {
    "shallow_hole": frozenset({"position", "dimensions"}),
    "blind_hole_too_shallow": frozenset({"position", "dimensions"}),
    "hole_depth": frozenset({"position", "dimensions"}),
    "edge_breakout": frozenset({"position", "dimensions", "interface_risk"}),
    "thin_wall": frozenset({"wall", "dimensions"}),
    "wall_too_thin": frozenset({"wall", "dimensions"}),
    "suspended_rib": frozenset({"position", "wall"}),
    "detached_rib": frozenset({"position", "wall"}),
    "floating_rib": frozenset({"position", "wall"}),
    "hole_blocked": frozenset({"position", "access"}),
    "access_blocked": frozenset({"position", "access"}),
    "assembly_eccentricity": frozenset({"position", "interface_risk"}),
    "eccentricity": frozenset({"position", "interface_risk"}),
    "axis_misalignment": frozenset({"position", "interface_risk"}),
    "interference": frozenset({"interface_risk"}),
}


@dataclass(frozen=True)
class SchemaIssue:
    path: str
    message: str
    issue_type: str = "SchemaError"
    severity: str = "error"  # "error" | "warning"
    hint: str | None = None

    def to_check(self, name: str = "design_schema") -> dict:
        payload = {
            "name": name,
            "type": "design_schema",
            "ok": self.severity != "error",
            "path": self.path,
            "severity": self.severity,
            "error": {"type": self.issue_type, "message": self.message},
        }
        if self.hint:
            payload["hint"] = self.hint
        return payload


def _issue(path: str, message: str, *, hint: str | None = None, severity: str = "error") -> SchemaIssue:
    return SchemaIssue(path=path, message=message, hint=hint, severity=severity)


def classify_feature(feature: dict) -> set[str]:
    """Classify a feature by its id, intent, and description text.

    Returns a set of tags: "hole", "load_bearing_attachment", "interface".
    """
    text = " ".join(str(feature.get(k, "")) for k in ("id", "description", "intent")).lower()
    tags: set[str] = set()
    if any(word in text for word in HOLE_WORDS):
        tags.add("hole")
    if any(word in text for word in ATTACHMENT_WORDS):
        tags.add("load_bearing_attachment")
    if any(word in text for word in INTERFACE_WORDS):
        tags.add("interface")
    return tags

def _required_evidence_from_payload(payload: dict[str, Any]) -> set[str]:
    raw = payload.get("required_evidence") or []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return set()
    normalized: set[str] = set()
    aliases = {
        "size": "dimensions",
        "dimension": "dimensions",
        "clearance": "interface_risk",
        "interface": "interface_risk",
        "risk": "interface_risk",
        "root": "wall",
        "wall_thickness": "wall",
        "tool_access": "access",
    }
    for item in raw:
        key = _norm_key(item)
        normalized.add(aliases.get(key, key))
    return normalized


def _iter_design_interfaces(design: dict[str, Any]) -> list[dict[str, Any]]:
    raw = design.get("interfaces")
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        rows = []
        for key, value in raw.items():
            if isinstance(value, dict):
                rows.append({"id": key, **value} if "id" not in value else value)
        return rows
    return []


def _iter_failure_modes(design: dict[str, Any]) -> list[dict[str, Any]]:
    raw = design.get("failure_modes")
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        rows = []
        for key, value in raw.items():
            if isinstance(value, dict):
                rows.append({"id": key, **value} if "id" not in value else value)
        return rows
    return []


def _feature_refs_for_intent(payload: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in ("feature_ids", "features", "affects"):
        raw = payload.get(key)
        if isinstance(raw, list):
            values.extend(raw)
    for key in ("feature_id", "feature", "feature_a", "feature_b"):
        if payload.get(key) is not None:
            values.append(payload.get(key))
    refs: list[str] = []
    for value in values:
        if isinstance(value, str) and value not in refs:
            refs.append(value)
    return refs


def _affects_for_failure(failure: dict[str, Any]) -> list[str]:
    return _feature_refs_for_intent(failure)


def _feature_ids(design: dict[str, Any]) -> set[str]:
    return {
        str(feature.get("id"))
        for feature in (design.get("features") or [])
        if isinstance(feature, dict) and feature.get("id")
    }

def _norm_key(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _num_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _triple_or_none(value: Any) -> tuple[float, float, float] | None:
    if not isinstance(value, list) or len(value) != 3:
        return None
    x = _num_or_none(value[0])
    y = _num_or_none(value[1])
    z = _num_or_none(value[2])
    if x is None or y is None or z is None:
        return None
    return x, y, z
