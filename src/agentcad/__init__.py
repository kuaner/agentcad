"""Agent-first CAD workflow runtime."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
import tomllib


def _read_pyproject_version() -> str | None:
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if not pyproject.exists():
        return None
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    project = data.get("project")
    if not isinstance(project, dict):
        return None
    value = project.get("version")
    return value if isinstance(value, str) else None


try:
    __version__ = _read_pyproject_version() or package_version("agentcad-cli")
except PackageNotFoundError:
    __version__ = "0+unknown"
