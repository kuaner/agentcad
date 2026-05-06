from __future__ import annotations

import json
import os
from pathlib import Path

from . import templates


PROJECT_FILE = "cadproject.json"


def write_if_missing(path: Path, text: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def write_json_if_missing(path: Path, payload: dict) -> bool:
    return write_if_missing(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def init_workspace(target: Path, force: bool = False) -> dict:
    target = target.expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    project_file = target / PROJECT_FILE
    if project_file.exists() and not force:
        return {"ok": True, "message": "workspace already exists", "project": str(target)}

    write_json_if_missing(project_file, templates.CADPROJECT_JSON)
    write_if_missing(target / "CLAUDE.md", templates.WORKSPACE_CLAUDE_MD)
    agents_link = target / "AGENTS.md"
    if not agents_link.exists():
        agents_link.symlink_to("CLAUDE.md")
    write_if_missing(target / "skills" / "build123d-guide.md", templates.SKILL_BUILD123D_GUIDE)
    write_if_missing(target / "skills" / "validation-strategy.md", templates.SKILL_VALIDATION_STRATEGY)
    write_if_missing(target / "skills" / "common-errors.md", templates.SKILL_COMMON_ERRORS)
    (target / "models").mkdir(exist_ok=True)
    (target / "references" / "images").mkdir(parents=True, exist_ok=True)
    write_if_missing(target / "references" / "notes.md", templates.REFERENCE_NOTES)
    return {"ok": True, "message": "workspace initialized", "project": str(target)}


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
    root.mkdir(parents=True, exist_ok=True)
    (root / "outputs").mkdir(exist_ok=True)
    write_if_missing(root / "README.md", templates.model_readme(safe))
    write_if_missing(root / "params.json", templates.model_params())
    write_if_missing(root / "design.json", templates.model_design(safe))
    write_if_missing(root / "part.py", templates.model_part())
    return {"ok": True, "message": "model created", "model": safe, "path": str(root)}


def normalize_model_name(name: str) -> str:
    value = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(name).strip())
    value = value.strip("_")
    if not value:
        raise ValueError("model name is required")
    return value
