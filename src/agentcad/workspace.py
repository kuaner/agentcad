from __future__ import annotations

import shutil
from pathlib import Path

from . import templates

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
