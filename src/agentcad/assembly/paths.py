from __future__ import annotations

from pathlib import Path

from ..workspace import normalize_model_name


def assemblies_dir(project: Path) -> Path:
    return project / "assemblies"


def assembly_dir(project: Path, name: str) -> Path:
    return assemblies_dir(project) / normalize_model_name(name)


def assembly_outputs_dir(project: Path, name: str) -> Path:
    return assembly_dir(project, name) / "outputs"
