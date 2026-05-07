"""Pre-delivery design self-review: a structured checklist for agents.

``cad review`` is the gatekeeper before ``cad deliver``.  It aggregates
artifacts from build / measure / validate, produces a relations matrix
between every pair of declared shapes, lists key SVGs that must be visually
inspected, and emits a JSON checklist the agent must address.

Unlike validate (which executes geometry checks) review focuses on
**meta-quality**: are all the failure modes that have *historically caused
silent issues* explicitly verified?

Output schema (all JSON):
  {
    "ok": bool,
    "ready_to_deliver": bool,
    "checklist": [{"id", "ok", "title", "evidence", "action"}, ...],
    "relations": [{"a","b","clearance_mm","ok"}, ...],
    "must_view": [{"label","path","why"}, ...],
    "open_warnings": [...],
    "deferred_followups": [...]
  }
"""
from __future__ import annotations

import itertools
from pathlib import Path
from typing import Any

from .geometry import min_clearance_3d, parse_shape
from .jsonio import read_json, write_json
from .runner import utc_now
from .workspace import model_dir, outputs_dir


def review_model(project: Path, name: str) -> dict:
    out_dir = outputs_dir(project, name)
    out_dir.mkdir(parents=True, exist_ok=True)
    review_path = out_dir / "review.json"

    design_path = model_dir(project, name) / "design.json"
    validation_path = out_dir / "validation.json"
    geometry_path = out_dir / "geometry.json"

    design = read_json(design_path, default=None)
    validation = read_json(validation_path, default=None)
    geometry = read_json(geometry_path, default=None)

    checklist: list[dict] = []

    checklist.append(_item(
        "design_present", design is not None,
        title="design.json exists and is parseable",
        action="run 'cad new <name>' to scaffold or fix syntax",
        evidence={"path": str(design_path)},
    ))
    if design is None:
        return _payload(name, checklist, [], [], [], review_path)

    checklist.append(_item(
        "validation_passes",
        bool(validation and validation.get("ok")),
        title="cad validate is green",
        action="run 'cad validate <name> --json' and fix the first failing check",
        evidence={
            "path": str(validation_path),
            "failed_checks": [
                c.get("name") for c in (validation or {}).get("checks", [])
                if not c.get("ok")
            ] if validation else [],
        },
    ))

    checklist.append(_item(
        "feature_coverage",
        _all_features_covered(design),
        title="every feature references at least one geometry check",
        action="link the feature to a check id via its 'checks' array",
        evidence={"features": [f.get("id") for f in design.get("features", [])]},
    ))

    has_clearance = _has_min_clearance_for_each_hole(design)
    checklist.append(_item(
        "hole_clearance_declared",
        has_clearance["ok"],
        title="every hole has a min_clearance check vs surrounding solids",
        action=(
            "add min_clearance checks: feature_a = the hole cylinder, "
            "feature_b = each adjacent wall/plate. This catches edge-overlap bugs."
        ),
        evidence=has_clearance,
    ))

    relations = _compute_all_pair_clearances(design)
    interferences = [r for r in relations if r.get("interferes")]
    checklist.append(_item(
        "no_pairwise_interference",
        not interferences,
        title="no declared shape pair interferes",
        action="separate interfering features (move/resize) — see 'relations' below",
        evidence={"interferences": interferences},
    ))

    must_view = _build_must_view_list(out_dir, design, validation)
    checklist.append(_item(
        "key_svgs_present",
        all(Path(item["path"]).exists() for item in must_view),
        title="key cross-section SVGs exist for visual review",
        action=(
            "run 'cad render <name> --section-z <z>' for each missing layer "
            "interface — review the SVGs visually"
        ),
        evidence={"sections": must_view},
    ))

    geom_warnings = (validation or {}).get("warnings") or []
    checklist.append(_item(
        "no_open_warnings", not geom_warnings,
        title="no open weak-check warnings",
        action="address each warning (typically by adding a stronger check)",
        evidence={"warnings": geom_warnings},
    ))

    bbox_actual = ((geometry or {}).get("geometry") or {}).get("bbox")
    bbox_match = _bbox_matches_intent(design, bbox_actual)
    checklist.append(_item(
        "bbox_matches_intent",
        bbox_match["ok"],
        title="measured bbox is consistent with declared intent",
        action="reconcile bbox_size check expected vs measured",
        evidence=bbox_match,
    ))

    deferred_followups = _deferred_followups(design, validation)

    payload = _payload(
        name, checklist, relations, must_view,
        deferred_followups, review_path,
        warnings=geom_warnings,
    )
    write_json(review_path, payload)
    return payload


# ── Helpers ─────────────────────────────────────────────────────────────────

def _item(item_id: str, ok: bool, title: str, action: str, evidence: Any) -> dict:
    return {
        "id": item_id,
        "ok": bool(ok),
        "title": title,
        "action": action if not ok else None,
        "evidence": evidence,
    }


def _all_features_covered(design: dict) -> bool:
    features = design.get("features") or []
    check_ids = {
        str(c.get("id")) for c in (design.get("checks") or [])
        if isinstance(c, dict) and c.get("id")
    }
    for feature in features:
        if not isinstance(feature, dict):
            return False
        linked = [str(cid) for cid in (feature.get("checks") or [])]
        if not linked or not any(cid in check_ids for cid in linked):
            return False
    return True


def _holes_in_design(design: dict) -> list[dict]:
    """Identify hole-shape descriptors declared inline on min_clearance checks.

    We treat every cylinder shape that appears as feature_a/feature_b in any
    min_clearance check as a "hole" candidate.  This is heuristic but enough
    to detect missing clearance declarations.
    """
    holes: list[dict] = []
    for c in design.get("checks") or []:
        if not isinstance(c, dict):
            continue
        for key in ("feature_a", "feature_b", "a", "b"):
            shape = c.get(key)
            if isinstance(shape, dict) and shape.get("type") == "cylinder":
                holes.append(shape)
    return holes


def _has_min_clearance_for_each_hole(design: dict) -> dict:
    """Soft heuristic: any feature whose intent contains 'hole' should have a clearance check."""
    features = design.get("features") or []
    hole_features = [
        f for f in features
        if isinstance(f, dict)
        and ("hole" in str(f.get("intent") or "").lower()
             or "hole" in str(f.get("id") or "").lower())
    ]
    clearance_checks = [
        c for c in design.get("checks") or []
        if isinstance(c, dict) and c.get("type") == "min_clearance"
    ]
    has_clearance = bool(clearance_checks)
    return {
        "ok": (not hole_features) or has_clearance,
        "hole_feature_count": len(hole_features),
        "min_clearance_check_count": len(clearance_checks),
    }


def _compute_all_pair_clearances(design: dict) -> list[dict]:
    """For every distinct pair of shape descriptors found in min_clearance
    checks, recompute the clearance and report it as a relation row.

    This produces the "relations matrix" the user asked about.
    """
    rows: list[dict] = []
    shape_index: dict[str, dict] = {}
    for c in design.get("checks") or []:
        if not isinstance(c, dict) or c.get("type") != "min_clearance":
            continue
        for key in ("feature_a", "feature_b"):
            shape = c.get(key)
            if not isinstance(shape, dict):
                continue
            try:
                parse_shape(shape)
            except ValueError:
                continue
            shape_index[_shape_key(shape)] = shape

    for (key_a, sa), (key_b, sb) in itertools.combinations(shape_index.items(), 2):
        try:
            result = min_clearance_3d(sa, sb)
        except (ValueError, KeyError):
            continue
        rows.append({
            "a": key_a,
            "b": key_b,
            "clearance_mm": result["clearance_mm"],
            "z_overlap_mm": result["z_overlap_mm"],
            "interferes": result["interferes"],
            "ok": not result["interferes"],
        })
    return rows


def _shape_key(shape: dict) -> str:
    """Compact stringy id for a shape descriptor (used in relations matrix)."""
    kind = shape.get("type")
    if kind == "cylinder":
        c = shape.get("center", [])
        return f"cyl({c[0]:.1f},{c[1]:.1f},r={shape.get('radius'):.2f})"
    if kind == "box":
        x = shape.get("x_range", [])
        y = shape.get("y_range", [])
        return f"box(x[{x[0]:.0f},{x[1]:.0f}],y[{y[0]:.0f},{y[1]:.0f}])"
    if kind == "sphere":
        c = shape.get("center", [])
        return f"sph({c[0]:.1f},{c[1]:.1f},{c[2]:.1f})"
    return f"{kind}"


def _build_must_view_list(out_dir: Path, design: dict, validation: dict | None) -> list[dict]:
    """Pick a small set of SVGs an agent / human MUST visually verify.

    Heuristic: include the iso preview + every section SVG that lies on a
    "layer interface" Z value (any shape's z_range endpoint that appears in
    multiple shapes).
    """
    items: list[dict] = []

    iso = out_dir / "preview.iso.svg"
    if iso.exists():
        items.append({
            "label": "iso_preview",
            "path": str(iso),
            "why": "overall shape — confirm topology matches intent",
        })

    z_layers = _interface_z_values(design)
    for z in z_layers:
        existing = list(out_dir.glob(f"section.z{z:.2f}.svg"))
        if existing:
            items.append({
                "label": f"section_z{z:.2f}",
                "path": str(existing[0]),
                "why": f"layer interface at Z={z:.2f} — verify hole vs wall layout",
            })

    if validation:
        for art_key, art_path in (validation.get("artifacts") or {}).items():
            if art_key.startswith("section_") and art_path:
                if art_path not in [it["path"] for it in items]:
                    items.append({
                        "label": art_key,
                        "path": art_path,
                        "why": "auto-scan section produced by validate",
                    })

    return items


def _interface_z_values(design: dict) -> list[float]:
    """Return Z values that appear as endpoints of multiple shapes.

    These are the most likely places for hole-wall interferences.
    """
    counts: dict[float, int] = {}
    for c in design.get("checks") or []:
        if not isinstance(c, dict):
            continue
        for key in ("feature_a", "feature_b"):
            shape = c.get(key)
            if not isinstance(shape, dict):
                continue
            try:
                z_range = shape.get("z_range")
                if not z_range:
                    continue
                for z in z_range:
                    counts[round(float(z), 2)] = counts.get(round(float(z), 2), 0) + 1
            except (TypeError, ValueError):
                continue
    return sorted(z for z, n in counts.items() if n >= 2)


def _bbox_matches_intent(design: dict, bbox_actual: Any) -> dict:
    if bbox_actual is None or not isinstance(bbox_actual, dict):
        return {"ok": False, "reason": "no measured bbox available — run measure"}
    expected = None
    for c in design.get("checks") or []:
        if isinstance(c, dict) and c.get("type") == "bbox_size":
            expected = c.get("expected")
            break
    if expected is None:
        return {"ok": True, "reason": "no bbox_size check declared", "actual": bbox_actual.get("size")}
    actual = bbox_actual.get("size")
    if not isinstance(actual, list) or not isinstance(expected, list) or len(actual) != len(expected):
        return {"ok": False, "expected": expected, "actual": actual}
    tolerance = 1.0  # 1mm slack for review-level sanity check
    matches = all(abs(float(a) - float(e)) <= tolerance for a, e in zip(actual, expected))
    return {"ok": matches, "expected": expected, "actual": actual, "tolerance": tolerance}


def _deferred_followups(design: dict, validation: dict | None) -> list[dict]:
    """Suggest next-step actions an agent should consider before delivering."""
    items: list[dict] = []
    weak = (validation or {}).get("warnings") or []
    for w in weak:
        items.append({
            "type": "weak_check",
            "feature": w.get("feature"),
            "hint": w.get("hint"),
        })

    holes = _holes_in_design(design)
    if holes and not any(c.get("type") == "hole_accessibility"
                         for c in design.get("checks") or []
                         if isinstance(c, dict)):
        items.append({
            "type": "missing_check_type",
            "hint": (
                "no hole_accessibility checks declared — consider adding one "
                "per hole to verify tool/bolt clearance"
            ),
        })

    return items


def _payload(
    name: str,
    checklist: list[dict],
    relations: list[dict],
    must_view: list[dict],
    deferred_followups: list[dict],
    review_path: Path,
    warnings: list[dict] | None = None,
) -> dict:
    ready = all(item.get("ok") for item in checklist)
    payload: dict[str, Any] = {
        "ok": ready,
        "stage": "review",
        "model": name,
        "reviewedAt": utc_now(),
        "ready_to_deliver": ready,
        "checklist": checklist,
        "relations": relations,
        "must_view": must_view,
        "deferred_followups": deferred_followups,
        "artifacts": {"review": str(review_path)},
        "message": (
            "review passed — ready to deliver" if ready
            else "review found issues — fix before deliver"
        ),
    }
    if warnings:
        payload["open_warnings"] = warnings
    return payload
