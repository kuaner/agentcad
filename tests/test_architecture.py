from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


MODULE_LINE_LIMITS = {
    "src/agentcad/assembly/core.py": 500,
    "src/agentcad/assembly/checks.py": 700,
    "src/agentcad/assembly/mesh.py": 550,
    "src/agentcad/assembly/references.py": 400,
    "src/agentcad/probe.py": 1250,
    "src/agentcad/contract.py": 1000,
    "src/agentcad/section.py": 900,
    "src/agentcad/suggest.py": 900,
    "src/agentcad/review.py": 650,
}

ASSEMBLY_PUBLIC_API = {
    "assemblies_dir",
    "assembly_dir",
    "assembly_outputs_dir",
    "init_assembly",
    "list_assemblies",
    "measure_assembly",
    "review_assembly",
    "validate_assembly",
}

FORBIDDEN_ASSEMBLY_IMPORTS = {
    "agentcad.batch",
    "agentcad.cli",
    "agentcad.doctor",
    "agentcad.probe",
    "agentcad.review",
    "agentcad.snapshot",
    "agentcad.suggest",
    "agentcad.validate",
}


def test_hot_modules_stay_under_explicit_line_ceilings():
    offenders = []
    for rel_path, limit in MODULE_LINE_LIMITS.items():
        path = ROOT / rel_path
        lines = len(path.read_text(encoding="utf-8").splitlines())
        if lines > limit:
            offenders.append(f"{rel_path}: {lines}>{limit}")

    assert not offenders, "Split responsibilities or update docs/ARCHITECTURE_GUARDRAILS.md: " + ", ".join(offenders)


def test_assembly_public_api_stays_package_based():
    assert not (ROOT / "src/agentcad/assembly.py").exists()

    import agentcad.assembly as assembly

    assert ASSEMBLY_PUBLIC_API <= set(assembly.__all__)


def test_assembly_internals_do_not_depend_on_workflow_frontends():
    offenders = []
    for path in sorted((ROOT / "src/agentcad/assembly").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            for imported in _imported_modules(node):
                if imported in FORBIDDEN_ASSEMBLY_IMPORTS:
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} imports {imported}")

    assert not offenders


def test_generated_files_are_not_tracked():
    result = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        pytest.skip("git metadata is unavailable")

    tracked = result.stdout.splitlines()
    generated = [
        path
        for path in tracked
        if "/__pycache__/" in path or path.endswith(".pyc") or path.endswith(".DS_Store")
    ]
    assert generated == []


def _imported_modules(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if not isinstance(node, ast.ImportFrom) or node.module is None:
        return []
    if node.level == 0:
        return [node.module]
    if node.level == 2:
        return [f"agentcad.{node.module}"]
    return []
