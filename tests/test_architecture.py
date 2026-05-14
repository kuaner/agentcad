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
    "src/agentcad/probe/core.py": 250,
    "src/agentcad/probe/execution.py": 450,
    "src/agentcad/probe/planner.py": 850,
    "src/agentcad/probe/utils.py": 120,
    "src/agentcad/contract/__init__.py": 120,
    "src/agentcad/contract/common.py": 260,
    "src/agentcad/contract/schema.py": 350,
    "src/agentcad/contract/evidence.py": 450,
    "src/agentcad/contract/weak.py": 150,
    "src/agentcad/contract/params.py": 80,
    "src/agentcad/suggest/__init__.py": 80,
    "src/agentcad/suggest/core.py": 250,
    "src/agentcad/suggest/facts.py": 220,
    "src/agentcad/suggest/geometry.py": 350,
    "src/agentcad/suggest/templates.py": 300,
    "src/agentcad/suggest/types.py": 80,
    "src/agentcad/section/__init__.py": 100,
    "src/agentcad/section/analysis.py": 350,
    "src/agentcad/section/cache.py": 80,
    "src/agentcad/section/extraction.py": 120,
    "src/agentcad/section/measure.py": 320,
    "src/agentcad/section/render.py": 220,
    "src/agentcad/section/types.py": 80,
    "src/agentcad/review.py": 650,
    "src/agentcad/validate.py": 650,
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

CONTRACT_PUBLIC_API = {
    "GEOMETRY_CHECK_TYPES",
    "HOLE_WORDS",
    "ROOT_CHECK_TYPES",
    "SchemaIssue",
    "_check_path",
    "_feature_path",
    "_issue",
    "_validate_check_by_type",
    "_validate_min_wall_thickness_check",
    "_validate_section_bbox_check",
    "classify_feature",
    "evaluate_design_intent_lint_dict",
    "evaluate_feature_coverage",
    "evaluate_feature_coverage_dict",
    "evaluate_feature_evidence_matrix_dict",
    "evaluate_weak_check_warnings",
    "evaluate_weak_check_warnings_dict",
    "search_params_by_keywords",
    "validate_design_schema",
    "validate_design_schema_dict",
    "validate_design_schema_issues",
}

SECTION_PUBLIC_API = {
    "AXIS_X",
    "AXIS_Y",
    "AXIS_Z",
    "SectionCache",
    "Segment2D",
    "_empty_svg",
    "analyze_section_segments",
    "measure_section_line",
    "measure_section_point",
    "measure_section_region",
    "query_section_measurements",
    "render_section_svg",
    "scan_profile",
    "section_segments",
    "write_section_svg",
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

FORBIDDEN_SECTION_IMPORTS = {
    "agentcad.assembly",
    "agentcad.batch",
    "agentcad.cli",
    "agentcad.contract",
    "agentcad.doctor",
    "agentcad.preview",
    "agentcad.probe",
    "agentcad.review",
    "agentcad.snapshot",
    "agentcad.suggest",
    "agentcad.validate",
}

FORBIDDEN_CONTRACT_IMPORTS = {
    "agentcad.assembly",
    "agentcad.batch",
    "agentcad.cli",
    "agentcad.doctor",
    "agentcad.preview",
    "agentcad.probe",
    "agentcad.render",
    "agentcad.review",
    "agentcad.snapshot",
    "agentcad.suggest",
    "agentcad.validate",
}

CONTRACT_SUBMODULE_IMPORTERS = {
    "src/agentcad/metadata.py",
    "src/agentcad/precheck.py",
    "src/agentcad/probe/core.py",
    "src/agentcad/probe/planner.py",
    "src/agentcad/review.py",
    "src/agentcad/suggest/core.py",
    "src/agentcad/suggest/facts.py",
    "src/agentcad/suggest/templates.py",
    "src/agentcad/validate.py",
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


def test_contract_public_api_stays_package_based():
    assert not (ROOT / "src/agentcad/contract.py").exists()

    import agentcad.contract as contract

    assert CONTRACT_PUBLIC_API <= set(contract.__all__)


def test_suggest_public_api_stays_package_based():
    assert not (ROOT / "src/agentcad/suggest.py").exists()

    import agentcad.suggest as suggest

    assert {"SuggestContext", "suggest_checks"} <= set(suggest.__all__)


def test_section_public_api_stays_package_based():
    assert not (ROOT / "src/agentcad/section.py").exists()

    import agentcad.section as section

    assert SECTION_PUBLIC_API <= set(section.__all__)


def test_assembly_internals_do_not_depend_on_workflow_frontends():
    offenders = []
    for path in sorted((ROOT / "src/agentcad/assembly").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            for imported in _imported_modules(node):
                if imported in FORBIDDEN_ASSEMBLY_IMPORTS:
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} imports {imported}")

    assert not offenders


def test_section_internals_do_not_depend_on_workflow_frontends():
    offenders = []
    for path in sorted((ROOT / "src/agentcad/section").glob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        current_module = _module_name_for_path(path)
        for node in ast.walk(tree):
            for imported in _imported_modules(node, current_module=current_module):
                for forbidden in FORBIDDEN_SECTION_IMPORTS:
                    if imported == forbidden or imported.startswith(f"{forbidden}."):
                        offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} imports {imported}")

    assert not offenders


def test_contract_internals_do_not_depend_on_workflow_frontends():
    offenders = []
    for path in sorted((ROOT / "src/agentcad/contract").glob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        current_module = _module_name_for_path(path)
        for node in ast.walk(tree):
            for imported in _imported_modules(node, current_module=current_module):
                for forbidden in FORBIDDEN_CONTRACT_IMPORTS:
                    if imported == forbidden or imported.startswith(f"{forbidden}."):
                        offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} imports {imported}")

    assert not offenders


def test_workflow_modules_import_contract_submodules_directly():
    offenders = []
    for rel_path in sorted(CONTRACT_SUBMODULE_IMPORTERS):
        path = ROOT / rel_path
        tree = ast.parse(path.read_text(encoding="utf-8"))
        current_module = _module_name_for_path(path)
        for node in ast.walk(tree):
            for imported in _imported_modules(node, current_module=current_module):
                if imported == "agentcad.contract":
                    offenders.append(f"{rel_path}:{node.lineno} imports contract root")

    assert not offenders


def test_suggest_depends_on_probe_planner_not_probe_execution():
    path = ROOT / "src/agentcad/suggest/core.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = {
        imported
        for node in ast.walk(tree)
        for imported in _imported_modules(node, current_module="agentcad.suggest.core")
    }

    assert "agentcad.probe.planner" in imports
    assert "agentcad.probe" not in imports
    assert "agentcad.probe.execution" not in imports


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


def _module_name_for_path(path: Path) -> str:
    rel = path.relative_to(ROOT / "src").with_suffix("")
    parts = rel.parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imported_modules(node: ast.AST, *, current_module: str | None = None) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if not isinstance(node, ast.ImportFrom) or node.module is None:
        return []
    if node.level == 0:
        return [node.module]
    if node.level == 2:
        return [f"agentcad.{node.module}"]
    if node.level == 1 and current_module and current_module.startswith("agentcad."):
        package = current_module.rsplit(".", 1)[0]
        return [f"{package}.{node.module}"]
    return []
