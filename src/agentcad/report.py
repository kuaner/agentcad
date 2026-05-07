from __future__ import annotations

from pathlib import Path

from .jsonio import read_json, write_json
from .workspace import outputs_dir


def report_model(project: Path, name: str) -> dict:
    """Generate a human-readable Markdown validation report.

    Reads the existing ``validation.json`` produced by ``agentcad validate`` and
    writes ``outputs/report.md``.  The Markdown is also returned in the payload
    under ``report`` so it can be streamed directly to the terminal.
    """
    out_dir = outputs_dir(project, name)
    validation_path = out_dir / "validation.json"

    if not validation_path.exists():
        return {
            "ok": False,
            "stage": "report",
            "model": name,
            "error": {
                "type": "ValidationMissing",
                "message": f"validation.json not found — run 'agentcad validate {name}' first",
            },
        }

    validation = read_json(validation_path, default={}) or {}
    md = _build_markdown(validation, name)
    report_path = out_dir / "report.md"
    report_path.write_text(md, encoding="utf-8")

    return {
        "ok": True,
        "stage": "report",
        "model": name,
        "report": md,
        "artifacts": {"report": str(report_path)},
        "message": f"report written to {report_path}",
    }


def _build_markdown(v: dict, name: str) -> str:
    ok = bool(v.get("ok"))
    status_badge = "✅ PASSED" if ok else "❌ FAILED"
    validated_at = v.get("validatedAt", "—")
    checks = v.get("checks") or []
    warnings = v.get("warnings") or []
    artifacts = v.get("artifacts") or {}

    lines: list[str] = [
        f"# Validation Report — `{name}`",
        "",
        f"**Status**: {status_badge}  ",
        f"**Validated at**: {validated_at}",
        "",
    ]

    # Stage results
    stage_checks = [c for c in checks if c.get("type") == "stage"]
    if stage_checks:
        lines += ["## Pipeline Stages", "", "| Stage | Status |", "|-------|--------|"]
        for c in stage_checks:
            icon = "✅" if c.get("ok") else "❌"
            err = f" — {c.get('error', {}).get('message', '')}" if not c.get("ok") else ""
            lines.append(f"| {c.get('name', '?')} | {icon}{err} |")
        lines.append("")

    # Design checks
    design_checks = [c for c in checks if c.get("type") not in ("stage", "feature_coverage")]
    feature_coverage = [c for c in checks if c.get("type") == "feature_coverage"]

    if design_checks:
        lines += ["## Design Checks", "", "| Check | Type | Status | Details |", "|-------|------|--------|---------|"]
        for c in design_checks:
            icon = "✅" if c.get("ok") else "❌"
            check_name = c.get("name", "?")
            check_type = c.get("type", "?")
            details = _format_check_details(c)
            lines.append(f"| {check_name} | {check_type} | {icon} | {details} |")
        lines.append("")

    # Feature coverage
    if feature_coverage:
        lines += ["## Feature Coverage", "", "| Feature | Status | Matched Checks |", "|---------|--------|----------------|"]
        for c in feature_coverage:
            icon = "✅" if c.get("ok") else "❌"
            feature = c.get("feature", "?")
            matched = ", ".join(str(x) for x in (c.get("matchedChecks") or [])) or "—"
            lines.append(f"| {feature} | {icon} | {matched} |")
        lines.append("")

    # Geometry warnings
    if warnings:
        lines += ["## Warnings", ""]
        for w in warnings:
            lines.append(f"> ⚠ {w.get('message', '')}")
            if hint := w.get("hint"):
                lines.append(f">")
                lines.append(f"> 💡 {hint}")
        lines.append("")

    # Artifacts
    if artifacts:
        lines += ["## Artifacts", "", "| Key | Path |", "|-----|------|"]
        for key, path in sorted(artifacts.items()):
            lines.append(f"| {key} | `{path}` |")
        lines.append("")

    return "\n".join(lines)


def _format_check_details(c: dict) -> str:
    check_type = c.get("type", "")
    if check_type == "bbox_size":
        expected = c.get("expected")
        actual = c.get("actual")
        tol = c.get("tolerance", 0)
        return f"expected {expected} ±{tol}, actual {actual}"
    if check_type == "watertight":
        return f"expected {c.get('expected')}, actual {c.get('actual')}"
    if check_type in ("outer_diameter_at_z", "inner_diameter_at_z"):
        z = c.get("z")
        expected = c.get("expected")
        actual = c.get("actual")
        tol = c.get("tolerance", 0)
        kind = "⌀outer" if "outer" in check_type else "⌀inner"
        actual_str = f"{actual:.2f}mm" if actual is not None else "—"
        return f"z={z}, {kind} expected {expected}±{tol}mm, actual {actual_str}"
    if check_type == "section_bbox_at_z":
        z = c.get("z")
        expected = c.get("expected")
        actual = c.get("actual")
        pts = c.get("region_point_count")
        return f"z={z}, expected {expected}, actual {actual} ({pts} pts)"
    if check_type == "volume_range":
        actual = c.get("actual")
        lo = c.get("min")
        hi = c.get("max")
        actual_str = f"{actual:.1f}mm³" if actual is not None else "—"
        return f"{actual_str} in [{lo}, {hi}]"
    if check_type == "min_triangles":
        return f"expected ≥{c.get('expected')}, actual {c.get('actual')}"
    if check_type == "metadata_equals":
        return f"path={c.get('path')}, expected {c.get('expected')!r}, actual {c.get('actual')!r}"
    err = c.get("error")
    if err:
        return str(err)
    return "—"
