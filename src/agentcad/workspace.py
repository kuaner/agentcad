from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import templates
from .jsonio import write_json

PROJECT_FILE = "cadproject.json"


def _copy_tree(
    src: Path,
    dst: Path,
    substitutions: dict[str, str] | None = None,
    overwrite: bool = False,
    include_paths: set[str] | None = None,
) -> list[str]:
    """Copy a template directory tree to dst.

    Files ending in .gitkeep create empty directories. All other files are
    written with optional ``{key}`` substitution. Existing files are skipped
    unless overwrite=True.
    """
    written: list[str] = []
    for src_file in sorted(src.rglob("*")):
        rel = src_file.relative_to(src)
        rel_posix = rel.as_posix()
        if include_paths is not None and rel_posix not in include_paths:
            continue
        dst_file = dst / rel

        if src_file.name == ".gitkeep":
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            continue

        if src_file.is_dir():
            dst_file.mkdir(parents=True, exist_ok=True)
            continue

        if dst_file.exists() and not overwrite:
            continue

        dst_file.parent.mkdir(parents=True, exist_ok=True)
        content = src_file.read_text(encoding="utf-8")
        if substitutions:
            content = content.replace("{name}", substitutions.get("name", ""))
        dst_file.write_text(content, encoding="utf-8")
        written.append(rel_posix)
    return written


def init_workspace(target: Path, force: bool = False) -> dict:
    target = target.expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    project_file = target / PROJECT_FILE
    if project_file.exists() and not force:
        return {"ok": True, "message": "workspace already exists", "project": str(target)}

    _copy_tree(templates.workspace_dir(), target)

    agents_link = target / "AGENTS.md"
    if not agents_link.exists():
        agents_link.symlink_to("CLAUDE.md")

    return {"ok": True, "message": "workspace initialized", "project": str(target)}


def sync_workspace(
    project: Path,
    *,
    dry_run: bool = False,
    only: str | None = None,
    prune_deprecated: bool = False,
) -> dict:
    """Re-apply workspace scaffold files (CLAUDE.md, references/, etc.) from templates."""
    target = project.expanduser().resolve()
    project_file = target / PROJECT_FILE
    if not project_file.exists():
        return {"ok": False, "stage": "sync", "error": {"type": "NotAWorkspace", "message": f"no {PROJECT_FILE} found in {target}"}}

    tpl = templates.workspace_dir()
    include: set[str] | None = None
    if only:
        only_posix = only.strip().lstrip("/").replace("\\", "/")
        matches = [p.relative_to(tpl).as_posix() for p in tpl.rglob("*") if p.is_file() and p.relative_to(tpl).as_posix().startswith(only_posix)]
        if not matches:
            return {"ok": False, "stage": "sync", "error": {"type": "PathNotInTemplate", "message": f"path not found in workspace templates: {only}"}}
        include = set(matches)

    planned = [p.relative_to(tpl).as_posix() for p in tpl.rglob("*") if p.is_file()]
    if include is not None:
        planned = [p for p in planned if p in include]
    should_sync_agents = include is None or "CLAUDE.md" in include
    if should_sync_agents:
        planned.append("AGENTS.md")

    pruned: list[str] = []
    deprecated = [target / "skills"]
    if prune_deprecated:
        for path in deprecated:
            if path.exists():
                pruned.append(str(path.relative_to(target)))
                if not dry_run:
                    if path.is_symlink():
                        path.unlink()
                    elif path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()

    written: list[str] = []
    if not dry_run:
        written = _copy_tree(tpl, target, overwrite=True, include_paths=include)

    agents_link = target / "AGENTS.md"
    if not dry_run and should_sync_agents:
        if agents_link.is_symlink() or agents_link.exists():
            agents_link.unlink()
        agents_link.symlink_to("CLAUDE.md")
        written.append("AGENTS.md")

    result = {
        "ok": True,
        "project": str(target),
        "dry_run": dry_run,
        "planned_updates": planned,
        "updated": written,
        "pruned": pruned,
        "message": "workspace scaffold previewed" if dry_run else "workspace scaffold updated",
    }
    if only:
        result["only"] = only
    result["agents_relinked"] = (not dry_run) and should_sync_agents
    return result


def find_project(path: Path) -> Path:
    current = path.expanduser().resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        if (candidate / PROJECT_FILE).exists():
            return candidate
    raise FileNotFoundError(f"No {PROJECT_FILE} found from {path}")


def model_dir(project: Path, name: str) -> Path:
    return project / "models" / name


def outputs_dir(project: Path, name: str) -> Path:
    return model_dir(project, name) / "outputs"


def list_models(project: Path) -> list[str]:
    """Return sorted list of model names in the workspace."""
    models_root = project / "models"
    if not models_root.is_dir():
        return []
    return sorted(
        entry.name for entry in models_root.iterdir()
        if entry.is_dir() and (entry / "design.json").exists()
    )


def new_model(project: Path, name: str, force: bool = False) -> dict:
    safe = normalize_model_name(name)
    root = model_dir(project, safe)
    if root.exists() and not force:
        return {"ok": False, "stage": "new", "error": {"type": "ModelExists", "message": f"model exists: {safe}"}}

    _copy_tree(templates.model_dir(), root, substitutions={"name": safe})
    # Ensure outputs/ exists even when templates don't contain placeholders.
    (root / "outputs").mkdir(parents=True, exist_ok=True)

    return {"ok": True, "message": "model created", "model": safe, "path": str(root)}


def normalize_model_name(name: str) -> str:
    value = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(name).strip())
    value = value.strip("_")
    if not value:
        raise ValueError("model name is required")
    return value


def parse_model_target(target: str) -> tuple[str, str | None]:
    """Parse 'model' or 'model:variant' into normalized names."""
    raw = str(target)
    if ":" not in raw:
        return normalize_model_name(raw), None
    model, variant = raw.rsplit(":", 1)
    if not model or not variant:
        raise ValueError(f"invalid target '{target}': both model and variant name required around ':'")
    return normalize_model_name(model), normalize_model_name(variant)


def format_model_target(name: str, variant: str | None = None) -> str:
    safe = normalize_model_name(name)
    return f"{safe}:{normalize_model_name(variant)}" if variant else safe


def variant_dir(project: Path, name: str, variant: str) -> Path:
    safe_variant = normalize_model_name(variant)
    return model_dir(project, name) / "variants" / safe_variant


def variant_params_path(project: Path, name: str, variant: str) -> Path:
    return variant_dir(project, name, variant) / "params.json"


def outputs_dir_for_variant(project: Path, name: str, variant: str | None = None) -> Path:
    base = outputs_dir(project, name)
    if variant is None:
        return base
    safe_variant = normalize_model_name(variant)
    return base / safe_variant


def new_variant(project: Path, name: str, variant: str, params: dict | None = None) -> dict:
    safe = normalize_model_name(name)
    safe_variant = normalize_model_name(variant)
    v_dir = variant_dir(project, safe, safe_variant)
    if v_dir.exists():
        return {"ok": False, "stage": "new_variant", "error": {"type": "VariantExists", "message": f"variant already exists: {safe_variant}"}}
    v_dir.mkdir(parents=True, exist_ok=True)
    if params is None:
        source_params = model_dir(project, name) / "params.json"
        if source_params.exists():
            params = json.loads(source_params.read_text(encoding="utf-8"))
        else:
            params = {}
    write_json(v_dir / "params.json", params)
    return {"ok": True, "message": "variant created", "model": name, "variant": safe_variant, "path": str(v_dir)}
