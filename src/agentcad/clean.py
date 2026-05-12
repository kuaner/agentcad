"""Clean command: remove accumulated debug and history artifacts.

``agentcad clean`` removes validation history, debug SVGs, and optionally
preview files. Never deletes STEP, STL, geometry, build, validation,
deliverable, or observability artifacts by default.

Output schema:
  {
    "ok": bool,
    "stage": "clean",
    "model": str | null,
    "dry_run": bool,
    "removed": [str, ...],
    "kept": [str, ...],
    "bytes_freed": int
  }
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .workspace import model_dir, outputs_dir, list_models

# Default retention limits.
DEFAULT_HISTORY_MAX = 10
DEFAULT_DEBUG_MAX = 20

# Artifacts that are NEVER deleted by default (protected).
_PROTECTED_EXTENSIONS = frozenset({
    ".step", ".stl", ".json", ".html",
})

# Protected JSON filenames (core workflow outputs).
_PROTECTED_JSON_NAMES = frozenset({
    "build.json",
    "geometry.json",
    "validation.json",
    "deliverable.json",
    "observability.json",
    "precheck.json",
    "review.json",
})

# Patterns for deletable artifacts.
_HISTORY_PATTERN = "validation-history/*.json"
_DEBUG_PATTERN = "debug.*"
_PREVIEW_SVG_PATTERN = "preview.*.svg"


def clean_model(
    project: Path,
    name: str,
    *,
    dry_run: bool = False,
    validation_history: bool = True,
    debug: bool = True,
    previews: bool = False,
    history_max: int = DEFAULT_HISTORY_MAX,
) -> dict[str, Any]:
    """Clean accumulated artifacts for a single model."""
    out_dir = outputs_dir(project, name)
    if not out_dir.exists():
        return {
            "ok": True,
            "stage": "clean",
            "model": name,
            "dry_run": dry_run,
            "removed": [],
            "kept": [],
            "bytes_freed": 0,
        }

    removed: list[str] = []
    kept: list[str] = []
    bytes_freed = 0

    # Validation history: keep the most recent N, remove the rest.
    if validation_history:
        history_dir = out_dir / "validation-history"
        if history_dir.exists():
            history_files = sorted(
                history_dir.glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for i, f in enumerate(history_files):
                if i >= history_max:
                    size = f.stat().st_size
                    if dry_run:
                        kept.append(str(f))
                    else:
                        f.unlink()
                        removed.append(str(f))
                        bytes_freed += size
                else:
                    kept.append(str(f))

    # Debug artifacts: SVGs and JSONs matching debug.* pattern.
    if debug:
        for f in out_dir.glob(_DEBUG_PATTERN):
            if _is_protected(f, out_dir):
                kept.append(str(f))
                continue
            size = f.stat().st_size
            if dry_run:
                kept.append(str(f))
            else:
                f.unlink()
                removed.append(str(f))
                bytes_freed += size

    # Preview SVGs: only if --previews is passed.
    if previews:
        for f in out_dir.glob(_PREVIEW_SVG_PATTERN):
            size = f.stat().st_size
            if dry_run:
                kept.append(str(f))
            else:
                f.unlink()
                removed.append(str(f))
                bytes_freed += size

    return {
        "ok": True,
        "stage": "clean",
        "model": name,
        "dry_run": dry_run,
        "removed": removed,
        "kept": kept,
        "bytes_freed": bytes_freed,
    }


def _is_protected(f: Path, out_dir: Path) -> bool:
    """Check whether an artifact file is protected from deletion."""
    if f.name in _PROTECTED_JSON_NAMES:
        return True
    if f.suffix in _PROTECTED_EXTENSIONS and f.name != f.parent.name + f.suffix:
        # Allow deletion of debug.json (not a core workflow output).
        if f.name.startswith("debug."):
            return False
        return True
    # STL and STEP files matching the model name are always protected.
    model_name = out_dir.parent.name
    if f.name in (f"{model_name}.stl", f"{model_name}.step"):
        return True
    return False


def _clean_all(
    project: Path,
    *,
    dry_run: bool = False,
    validation_history: bool = True,
    debug: bool = True,
    previews: bool = False,
    history_max: int = DEFAULT_HISTORY_MAX,
) -> dict[str, Any]:
    """Clean accumulated artifacts for all models in the workspace."""
    models = list_models(project)
    per_model: list[dict] = []
    total_bytes = 0
    total_removed: list[str] = []
    for name in models:
        result = clean_model(
            project, name,
            dry_run=dry_run,
            validation_history=validation_history,
            debug=debug,
            previews=previews,
            history_max=history_max,
        )
        per_model.append(result)
        total_bytes += result["bytes_freed"]
        total_removed.extend(result["removed"])

    return {
        "ok": True,
        "stage": "clean",
        "model": None,
        "dry_run": dry_run,
        "models": per_model,
        "removed": total_removed,
        "bytes_freed": total_bytes,
    }