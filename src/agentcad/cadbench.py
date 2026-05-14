from __future__ import annotations

from pathlib import Path
from typing import Any

from .contract.evidence import evaluate_feature_evidence_matrix_dict
from .contract.schema import validate_design_schema_dict
from .jsonio import read_json
from .suggest import suggest_from_contract

EXPECTED_FIELDS = frozenset({
    "feature",
    "failure_mode",
    "required_evidence",
    "checks",
    "suggested_checks",
    "probe_command_contains",
    "max_placeholder_count",
})


def evaluate_cadbench_case(case_dir: Path) -> dict[str, Any]:
    """Evaluate one CADBench contract fixture."""
    case_dir = Path(case_dir)
    case_name = case_dir.name
    prompt_path = case_dir / "prompt.md"
    design_path = case_dir / "design.json"
    expected_path = case_dir / "expected.json"

    file_checks = [
        _check("prompt_present", prompt_path.exists(), {"path": str(prompt_path)}),
        _check("design_present", design_path.exists(), {"path": str(design_path)}),
        _check("expected_present", expected_path.exists(), {"path": str(expected_path)}),
    ]
    if not all(item["ok"] for item in file_checks):
        return _case_payload(case_name, case_dir, file_checks, metrics={})

    design = read_json(design_path, default=None)
    expected = read_json(expected_path, default=None)
    if not isinstance(design, dict) or not isinstance(expected, dict):
        checks = [
            *file_checks,
            _check("design_json_object", isinstance(design, dict), {"path": str(design_path)}),
            _check("expected_json_object", isinstance(expected, dict), {"path": str(expected_path)}),
        ]
        return _case_payload(case_name, case_dir, checks, metrics={})

    expected_schema = _expected_schema_check(expected)
    schema_issues = validate_design_schema_dict(design)
    design_schema = _check("design_schema", not schema_issues, {"issues": schema_issues})

    params = _read_optional_case_json(case_dir, "params.json")
    metadata = _read_optional_case_json(case_dir, "metadata.json")
    geometry = _read_optional_case_json(case_dir, "geometry.json")
    validation = _read_optional_case_json(case_dir, "validation.json")
    observability = _read_optional_case_json(case_dir, "observability.json")

    suggest = suggest_from_contract(
        case_name,
        design,
        params=params,
        metadata=metadata,
        geometry=geometry,
        validation=validation,
        observability=observability,
    )
    matrix = evaluate_feature_evidence_matrix_dict(design)
    feature = str(expected.get("feature") or "")
    row = next((item for item in matrix if item.get("feature") == feature), None)

    required_evidence = _as_string_list(expected.get("required_evidence"))
    actual_evidence = set(row.get("required_evidence") or []) if row else set()
    missing_evidence = sorted(set(required_evidence) - actual_evidence)
    evidence_check = _check(
        "required_evidence_covered",
        bool(row) and not missing_evidence,
        {
            "feature": feature,
            "expected": required_evidence,
            "actual": sorted(actual_evidence),
            "missing": missing_evidence,
        },
    )

    declared_types = _declared_check_types(design, feature)
    suggested_types = _suggested_template_types(suggest.get("suggestions") or [], feature=feature)
    candidate_types = declared_types | suggested_types
    expected_checks = set(_as_string_list(expected.get("checks")))
    missing_checks = sorted(expected_checks - candidate_types)
    check_coverage = _check(
        "candidate_check_types_covered",
        not missing_checks,
        {
            "expected": sorted(expected_checks),
            "declared": sorted(declared_types),
            "suggested": sorted(suggested_types),
            "missing": missing_checks,
        },
    )

    expected_suggested = set(_as_string_list(expected.get("suggested_checks")))
    missing_suggested = sorted(expected_suggested - suggested_types)
    suggested_coverage = _check(
        "suggested_check_types_covered",
        not missing_suggested,
        {
            "expected": sorted(expected_suggested),
            "actual": sorted(suggested_types),
            "missing": missing_suggested,
        },
    )

    quality = suggest.get("suggestion_quality") or {}
    max_placeholders = int(expected.get("max_placeholder_count", 0))
    placeholder_count = int(quality.get("placeholder_count", 0))
    placeholder_check = _check(
        "placeholder_budget",
        placeholder_count <= max_placeholders,
        {
            "placeholder_count": placeholder_count,
            "max_placeholder_count": max_placeholders,
            "placeholders": quality.get("placeholders") or [],
        },
    )

    commands = [
        str(item.get("command") or "")
        for item in (suggest.get("probe_plan") or [])
        if isinstance(item, dict)
    ]
    probe_fragments = _as_string_list(expected.get("probe_command_contains"))
    probe_hits = [
        {"fragment": fragment, "ok": any(fragment in command for command in commands)}
        for fragment in probe_fragments
    ]
    probe_check = _check(
        "probe_expectations_covered",
        bool(probe_hits) and all(item["ok"] for item in probe_hits),
        {"expected_fragments": probe_fragments, "hits": probe_hits, "commands": commands},
    )

    metrics = {
        "feature": feature,
        "failure_mode": expected.get("failure_mode"),
        "required_evidence": evidence_check["evidence"],
        "check_coverage": check_coverage["evidence"],
        "suggested_check_coverage": suggested_coverage["evidence"],
        "placeholder_count": placeholder_count,
        "placeholder_ratio": quality.get("placeholder_ratio", 0.0),
        "concrete_template_count": quality.get("concrete_template_count", 0),
        "probe_expectations": probe_check["evidence"],
    }
    checks = [
        *file_checks,
        expected_schema,
        design_schema,
        evidence_check,
        check_coverage,
        suggested_coverage,
        placeholder_check,
        probe_check,
    ]
    return _case_payload(case_name, case_dir, checks, metrics=metrics, suggest=suggest)


def evaluate_cadbench(root: Path) -> dict[str, Any]:
    """Evaluate all CADBench fixture directories below root."""
    root = Path(root)
    case_dirs = sorted(path for path in root.iterdir() if path.is_dir()) if root.exists() else []
    cases = [evaluate_cadbench_case(case_dir) for case_dir in case_dirs if (case_dir / "expected.json").exists()]
    failed_cases = [case["case"] for case in cases if not case.get("ok")]
    passed_cases = [case["case"] for case in cases if case.get("ok")]
    placeholder_count = sum(int((case.get("metrics") or {}).get("placeholder_count", 0)) for case in cases)
    metrics = {
        "placeholder_count": placeholder_count,
        "case_placeholder_counts": {
            case["case"]: int((case.get("metrics") or {}).get("placeholder_count", 0))
            for case in cases
        },
        "evidence_covered": sum(
            1 for case in cases
            if _case_check(case, "required_evidence_covered").get("ok")
        ),
        "check_types_covered": sum(
            1 for case in cases
            if _case_check(case, "candidate_check_types_covered").get("ok")
        ),
        "suggested_check_types_covered": sum(
            1 for case in cases
            if _case_check(case, "suggested_check_types_covered").get("ok")
        ),
        "probe_expectations_covered": sum(
            1 for case in cases
            if _case_check(case, "probe_expectations_covered").get("ok")
        ),
    }
    return {
        "ok": bool(cases) and not failed_cases,
        "stage": "cadbench",
        "root": str(root),
        "case_count": len(cases),
        "passed": len(passed_cases),
        "failed": len(failed_cases),
        "passed_cases": passed_cases,
        "failed_cases": failed_cases,
        "metrics": metrics,
        "cases": cases,
    }


def _case_payload(
    case_name: str,
    case_dir: Path,
    checks: list[dict[str, Any]],
    *,
    metrics: dict[str, Any],
    suggest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": all(item.get("ok") for item in checks),
        "stage": "cadbench_case",
        "case": case_name,
        "path": str(case_dir),
        "checks": checks,
        "metrics": metrics,
    }
    if suggest is not None:
        payload["suggestion_quality"] = suggest.get("suggestion_quality")
        payload["suggestion_count"] = len(suggest.get("suggestions") or [])
        payload["probe_count"] = len(suggest.get("probe_plan") or [])
    return payload


def _check(name: str, ok: bool, evidence: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "evidence": evidence}


def _expected_schema_check(expected: dict[str, Any]) -> dict[str, Any]:
    missing = sorted(EXPECTED_FIELDS - set(expected))
    invalid: list[str] = []
    for key in ("required_evidence", "checks", "suggested_checks"):
        if key in expected and not isinstance(expected[key], list):
            invalid.append(key)
    if "probe_command_contains" in expected and not isinstance(expected["probe_command_contains"], (str, list)):
        invalid.append("probe_command_contains")
    if "max_placeholder_count" in expected and not isinstance(expected["max_placeholder_count"], int):
        invalid.append("max_placeholder_count")
    return _check("expected_schema", not missing and not invalid, {"missing": missing, "invalid": sorted(invalid)})


def _read_optional_case_json(case_dir: Path, name: str) -> dict[str, Any]:
    payload = read_json(case_dir / name, default={})
    return payload if isinstance(payload, dict) else {}


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _declared_check_types(design: dict[str, Any], feature: str) -> set[str]:
    check_map = {
        str(check.get("id")): str(check.get("type"))
        for check in (design.get("checks") or [])
        if isinstance(check, dict) and check.get("id") and check.get("type")
    }
    linked: set[str] = set()
    for item in design.get("features") or []:
        if not isinstance(item, dict) or str(item.get("id")) != feature:
            continue
        for check_id in item.get("checks") or []:
            check_type = check_map.get(str(check_id))
            if check_type:
                linked.add(check_type)
    if linked:
        return linked
    return set(check_map.values())


def _suggested_template_types(suggestions: list[dict[str, Any]], *, feature: str) -> set[str]:
    types: set[str] = set()
    for suggestion in suggestions:
        if feature and str(suggestion.get("feature")) != feature:
            continue
        template = suggestion.get("template")
        if isinstance(template, dict) and template.get("type"):
            types.add(str(template["type"]))
    return types


def _case_check(case: dict[str, Any], name: str) -> dict[str, Any]:
    for check in case.get("checks") or []:
        if check.get("name") == name:
            return check
    return {}
