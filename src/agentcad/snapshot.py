"""Regression snapshot system for tracking validation result drift.

Snapshots normalize volatile fields (timestamps, paths, durations) and
record stable metrics (check IDs, bbox, volume, triangles, artifact
presence). Comparison reports check status drift, geometry drift, and
artifact changes between current and baseline results.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .jsonio import read_json, write_json

SNAPSHOT_SCHEMA = "agentcad.snapshot.v1"

DEFAULT_SNAPSHOT_TOLERANCES = {
    "bbox_abs_mm": 0.05,
    "volume_rel": 0.005,
    "triangles_abs": 0,
}


def snapshot_target(
    project: Path,
    target: dict,
    payload: dict,
) -> dict:
    """Create a normalized snapshot from a validation payload.

    Keeps only stable check metrics, geometry summaries, and artifact
    presence flags.
    """
    checks = payload.get("checks") or []
    check_summary: dict[str, dict] = {}
    for index, c in enumerate(checks):
        cid = c.get("name") or c.get("id") or f"check_{index}"
        check_summary[cid] = {
            "type": c.get("type"),
            "ok": bool(c.get("ok")),
        }
        # Preserve actual values for geometry-oriented check types.
        if c.get("actual") is not None:
            check_summary[cid]["actual"] = c.get("actual")

    geometry = _extract_geometry_metrics(payload)

    # Try reading the generated geometry artifact for richer stable metrics.
    kind = target.get("kind", "model")
    name = target.get("name", "")
    variant = target.get("variant")
    geo_path: Path | None = None
    artifact_geometry = (payload.get("artifacts") or {}).get("geometry")
    if isinstance(artifact_geometry, str) and artifact_geometry:
        geo_path = Path(artifact_geometry)
    if kind == "model" and name:
        from .workspace import outputs_dir_for_variant
        geo_path = geo_path or outputs_dir_for_variant(project, name, variant) / "geometry.json"
    elif kind == "assembly" and name:
        from .assembly import assembly_outputs_dir
        geo_path = geo_path or assembly_outputs_dir(project, name) / "assembly_geometry.json"
    if geo_path is not None:
        geo_data = read_json(geo_path, default=None)
        if isinstance(geo_data, dict):
            geometry.update({k: v for k, v in _extract_geometry_metrics(geo_data).items() if k not in geometry})

    # Determine artifact presence from payload.
    artifacts = payload.get("artifacts") or {}
    artifact_presence: dict[str, bool] = {}
    for key, path_str in artifacts.items():
        if isinstance(path_str, str) and path_str:
            artifact_presence[key] = Path(path_str).exists()

    return {
        "schema": SNAPSHOT_SCHEMA,
        "target": {
            "kind": kind,
            "name": name,
            "variant": variant,
        },
        "checks": check_summary,
        "geometry": geometry,
        "artifacts": artifact_presence,
    }


def _extract_geometry_metrics(payload: dict) -> dict[str, Any]:
    """Extract stable geometry metrics from validation or geometry payloads."""
    geometry: dict[str, Any] = {}

    def set_if_missing(key: str, value: Any) -> None:
        if value is not None and key not in geometry:
            geometry[key] = value

    def visit(data: Any) -> None:
        if not isinstance(data, dict):
            return
        set_if_missing("bbox_size", data.get("bbox_size"))
        set_if_missing("volume", data.get("volume"))
        set_if_missing("triangles", data.get("triangles"))
        set_if_missing("mesh_stats", data.get("mesh_stats"))

        bbox = data.get("bbox")
        if isinstance(bbox, dict):
            set_if_missing("bbox_size", bbox.get("size"))

        mesh = data.get("mesh")
        if isinstance(mesh, dict):
            set_if_missing("triangles", mesh.get("triangles"))
            set_if_missing("mesh_stats", mesh)

        mass = data.get("mass_properties")
        if isinstance(mass, dict):
            set_if_missing("volume", mass.get("volume"))

        assembly_geometry = data.get("assembly_geometry") or data.get("geometry_summary")
        if isinstance(assembly_geometry, dict):
            set_if_missing("triangles", assembly_geometry.get("triangle_count"))
            assembly_bbox = assembly_geometry.get("bbox")
            if isinstance(assembly_bbox, dict):
                set_if_missing("bbox_size", assembly_bbox.get("size"))

    visit(payload)
    visit(payload.get("geometry"))
    visit(payload.get("geometry_summary"))
    visit(payload.get("assembly_geometry"))
    return geometry


def _snapshot_path(project: Path, target: dict) -> Path:
    """Resolve snapshot file path from target descriptor."""
    kind = target.get("kind", "model")
    name = target.get("name", "")
    variant = target.get("variant")
    filename = _snapshot_filename(kind, name, variant)
    kind_dir = "models" if kind == "model" else "assemblies"
    return project / ".agentcad" / "snapshots" / kind_dir / filename


def write_snapshot(
    project: Path,
    target: dict,
    payload: dict,
) -> Path:
    """Write a normalized snapshot to .agentcad/snapshots/."""
    snap = snapshot_target(project, target, payload)
    output_path = _snapshot_path(project, target)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(output_path, snap)
    return output_path


def load_snapshot(
    project: Path,
    target: dict,
) -> dict | None:
    """Load a snapshot from .agentcad/snapshots/ if it exists."""
    path = _snapshot_path(project, target)
    return read_json(path, default=None)


def compare_snapshot(
    current: dict,
    baseline: dict,
    *,
    tolerances: dict | None = None,
) -> dict:
    """Compare current snapshot against baseline and report drift.

    Returns a comparison report with check regressions, geometry drift,
    and artifact changes.
    """
    tol = tolerances or DEFAULT_SNAPSHOT_TOLERANCES
    current_checks = current.get("checks") or {}
    baseline_checks = baseline.get("checks") or {}
    current_geo = current.get("geometry") or {}
    baseline_geo = baseline.get("geometry") or {}
    current_artifacts = current.get("artifacts") or {}
    baseline_artifacts = baseline.get("artifacts") or {}

    # Check drift.
    checks_regressed = []
    checks_fixed = []
    checks_added = []
    checks_removed = []

    for cid, c_data in current_checks.items():
        b_data = baseline_checks.get(cid)
        if b_data is None:
            checks_added.append(cid)
        elif c_data.get("ok") and not b_data.get("ok"):
            checks_fixed.append(cid)
        elif not c_data.get("ok") and b_data.get("ok"):
            checks_regressed.append(cid)

    for cid in baseline_checks:
        if cid not in current_checks:
            checks_removed.append(cid)

    # Geometry drift.
    geometry_drift: dict[str, Any] = {}
    for key in ("bbox_size", "volume", "triangles"):
        c_val = current_geo.get(key)
        b_val = baseline_geo.get(key)
        if c_val is None or b_val is None:
            continue
        if key == "bbox_size":
            delta = _drift_list(c_val, b_val, tol.get("bbox_abs_mm", 0.05))
            if delta:
                geometry_drift["bbox_size_delta"] = delta
        elif key == "volume":
            delta = _drift_relative(c_val, b_val, tol.get("volume_rel", 0.005))
            if delta is not None:
                geometry_drift["volume_delta"] = delta
        elif key == "triangles":
            delta = _drift_abs_int(c_val, b_val, tol.get("triangles_abs", 0))
            if delta is not None:
                geometry_drift["triangles_delta"] = delta

    # Artifact drift.
    artifact_changes: list[str] = []
    for key in current_artifacts:
        if key not in baseline_artifacts:
            artifact_changes.append(f"added: {key}")
        elif current_artifacts[key] != baseline_artifacts[key]:
            artifact_changes.append(f"changed: {key}")
    for key in baseline_artifacts:
        if key not in current_artifacts:
            artifact_changes.append(f"removed: {key}")

    ok = (
        not checks_regressed
        and not geometry_drift
        and not artifact_changes
    )

    return {
        "ok": ok,
        "stage": "snapshot_compare",
        "target": current.get("target") or {},
        "changes": {
            "checks_regressed": checks_regressed,
            "checks_fixed": checks_fixed,
            "checks_added": checks_added,
            "checks_removed": checks_removed,
            "geometry_drift": geometry_drift,
            "artifact_changes": artifact_changes,
        },
    }


def _snapshot_filename(kind: str, name: str, variant: str | None) -> str:
    if variant:
        safe_v = variant.replace("/", "_")
        return f"{name}__variant_{safe_v}.json"
    return f"{name}.json"


def _drift_list(current: list, baseline: list, tolerance: float) -> list | None:
    """Return per-element deltas if any exceeds tolerance.

    Length mismatches are treated as drift (shape change).
    """
    if len(current) != len(baseline):
        return [abs(c - b) for c, b in zip(current, baseline)] or [0.0]
    deltas = [abs(c - b) for c, b in zip(current, baseline)]
    if any(d > tolerance for d in deltas):
        return deltas
    return None


def _drift_relative(current: float, baseline: float, rel_tol: float) -> float | None:
    """Return delta if relative change exceeds tolerance."""
    if baseline == 0:
        return None
    delta = abs(current - baseline)
    if delta / abs(baseline) > rel_tol:
        return delta
    return None


def _drift_abs_int(current: int, baseline: int, abs_tol: int) -> int | None:
    """Return delta if absolute change exceeds tolerance."""
    delta = abs(current - baseline)
    if delta > abs_tol:
        return delta
    return None
