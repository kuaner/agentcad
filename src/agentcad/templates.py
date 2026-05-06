from __future__ import annotations

import importlib.resources
from pathlib import Path


def _templates_dir() -> Path:
    """Return the path to the _templates package directory."""
    ref = importlib.resources.files("agentcad._templates")
    # importlib.resources may return a Traversable; cast to Path
    return Path(str(ref))


def workspace_dir() -> Path:
    """Path to the workspace template tree."""
    return _templates_dir() / "workspace"


def model_dir() -> Path:
    """Path to the model template tree."""
    return _templates_dir() / "model"
