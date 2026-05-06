from __future__ import annotations

import importlib.resources
import json


def _read_text(filename: str) -> str:
    """Read a template file from the templates package."""
    return importlib.resources.files("agentcad._templates").joinpath(filename).read_text(encoding="utf-8")


# Static templates — loaded once at module level

CADPROJECT_JSON = json.loads(_read_text("cadproject.json"))

WORKSPACE_CLAUDE_MD = _read_text("workspace-claude.md")

SKILL_BUILD123D_GUIDE = _read_text("build123d-guide.md")

SKILL_VALIDATION_STRATEGY = _read_text("validation-strategy.md")

REFERENCE_NOTES = _read_text("reference-notes.md")


# Dynamic templates — {name} placeholder replaced at call time

def model_readme(name: str) -> str:
    return _read_text("model-readme.md").replace("{name}", name)


def model_params() -> str:
    return _read_text("model-params.json")


def model_design(name: str) -> str:
    return _read_text("model-design.json").replace("{name}", name)


def model_part() -> str:
    return _read_text("model-part.py")
