"""Batch validation and target discovery for workspace-level operations.

This module provides discovery functions that scan a workspace for models,
variants, and assemblies without running any CAD builds.  The batch runner
orchestrates existing single-target validators into a project-level report.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from .jsonio import write_json


@dataclass(frozen=True)
class ValidationTarget:
    kind: str              # "model" | "assembly"
    name: str
    variant: str | None
    path: Path
    slow: bool = False

    @property
    def display_name(self) -> str:
        if self.variant:
            return f"{self.name}:{self.variant}"
        return self.name


def discover_models(project: Path) -> list[ValidationTarget]:
    """Discover models with a design.json under models/*/."""
    models_root = project / "models"
    if not models_root.is_dir():
        return []
    targets = []
    for entry in sorted(models_root.iterdir()):
        if not entry.is_dir():
            continue
        design_path = entry / "design.json"
        if not design_path.exists():
            continue
        targets.append(ValidationTarget(
            kind="model",
            name=entry.name,
            variant=None,
            path=entry,
        ))
    return targets


def discover_variants(project: Path, model: str) -> list[ValidationTarget]:
    """Discover variants under models/<model>/variants/*/."""
    variants_root = project / "models" / model / "variants"
    if not variants_root.is_dir():
        return []
    targets = []
    for entry in sorted(variants_root.iterdir()):
        if not entry.is_dir():
            continue
        params_path = entry / "params.json"
        if not params_path.exists():
            continue
        targets.append(ValidationTarget(
            kind="model",
            name=model,
            variant=entry.name,
            path=entry,
        ))
    return targets


def discover_assemblies(project: Path) -> list[ValidationTarget]:
    """Discover assemblies with an assembly.json under assemblies/*/."""
    assemblies_root = project / "assemblies"
    if not assemblies_root.is_dir():
        return []
    targets = []
    for entry in sorted(assemblies_root.iterdir()):
        if not entry.is_dir():
            continue
        contract_path = entry / "assembly.json"
        if not contract_path.exists():
            continue
        targets.append(ValidationTarget(
            kind="assembly",
            name=entry.name,
            variant=None,
            path=entry,
        ))
    return targets


def discover_validation_targets(
    project: Path,
    *,
    include_models: bool = True,
    include_assemblies: bool = True,
    include_variants: bool = False,
    include_slow: bool = False,
) -> list[ValidationTarget]:
    """Discover all validation targets in the workspace.

    Returns a deterministic sorted list by (kind, name, variant).
    """
    targets: list[ValidationTarget] = []

    if include_models:
        models = discover_models(project)
        targets.extend(models)
        if include_variants:
            for m in models:
                targets.extend(discover_variants(project, m.name))

    if include_assemblies:
        targets.extend(discover_assemblies(project))

    # Sort deterministically by kind, name, variant.
    targets.sort(key=lambda t: (t.kind, t.name, t.variant or ""))

    if not include_slow:
        targets = [t for t in targets if not t.slow]

    return targets


def validate_target(project: Path, target: ValidationTarget) -> dict:
    """Run validation for a single target, dispatching to the correct validator."""
    if target.kind == "model":
        from .validate import validate_model
        return validate_model(project, target.name, variant=target.variant)
    if target.kind == "assembly":
        from .assembly import validate_assembly
        return validate_assembly(project, target.name)
    raise ValueError(f"unknown target kind: {target.kind}")


def _target_summary(target: ValidationTarget, payload: dict) -> dict:
    """Extract a concise summary from a full validation payload.

    Strips large nested data (section analyses, full geometry, preview HTML)
    so all.json remains reviewable without opening individual reports.
    """
    return {
        "kind": target.kind,
        "name": target.name,
        "variant": target.variant,
        "ok": bool(payload.get("ok")),
        "stage": payload.get("stage"),
        "message": payload.get("message"),
        "checks": _check_summary(payload.get("checks") or []),
        "warnings": payload.get("warnings") or [],
        "artifacts": payload.get("artifacts") or {},
        "error": payload.get("error"),
    }


def _check_summary(checks: list[dict]) -> list[dict]:
    """Reduce check payloads to status + name + type only."""
    return [
        {
            "name": c.get("name"),
            "type": c.get("type"),
            "ok": bool(c.get("ok")),
        }
        for c in checks
    ]


def validate_all(
    project: Path,
    *,
    include_models: bool = True,
    include_assemblies: bool = True,
    include_variants: bool = False,
    include_slow: bool = False,
    fail_fast: bool = False,
    output: Path | None = None,
) -> dict:
    """Validate all targets in the workspace and produce a project-level report."""
    start = perf_counter()
    targets = discover_validation_targets(
        project,
        include_models=include_models,
        include_assemblies=include_assemblies,
        include_variants=include_variants,
        include_slow=include_slow,
    )

    summaries: list[dict] = []
    for target in targets:
        result = validate_target(project, target)
        summaries.append(_target_summary(target, result))
        if fail_fast and not result.get("ok"):
            break

    passed = sum(1 for s in summaries if s["ok"])
    failed = sum(1 for s in summaries if not s["ok"])
    total_duration = round((perf_counter() - start) * 1000, 3)

    payload = {
        "ok": failed == 0,
        "stage": "validate_all",
        "project": str(project),
        "summary": {
            "total": len(targets),
            "passed": passed,
            "failed": failed,
            "skipped": len(targets) - len(summaries),
            "durationMs": total_duration,
        },
        "targets": summaries,
        "artifacts": {},
    }

    output_path = output or project / ".agentcad" / "validation" / "all.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(output_path, payload)
    payload["artifacts"]["validation_all"] = str(output_path)
    return payload