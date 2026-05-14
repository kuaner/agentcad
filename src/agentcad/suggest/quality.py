from __future__ import annotations

import re
from typing import Any

_PLACEHOLDER_RE = re.compile(r"<[^<>]+>")


def evaluate_suggestion_quality(suggestions: list[dict[str, Any]]) -> dict[str, Any]:
    """Return deterministic concreteness metrics for suggested templates."""
    template_count = len([s for s in suggestions if "template" in s])
    placeholders: list[dict[str, Any]] = []
    concrete_template_count = 0
    for suggestion in suggestions:
        if "template" not in suggestion:
            continue
        local: list[dict[str, Any]] = []
        _collect_placeholders(
            suggestion.get("template"),
            path="template",
            feature=str(suggestion.get("feature", "")),
            missing=str(suggestion.get("missing", "")),
            out=local,
        )
        placeholders.extend(local)
        if not local:
            concrete_template_count += 1
    placeholder_count = len(placeholders)
    return {
        "template_count": template_count,
        "placeholder_count": placeholder_count,
        "placeholder_ratio": (placeholder_count / template_count) if template_count else 0.0,
        "placeholders": placeholders,
        "concrete_template_count": concrete_template_count,
    }


def _collect_placeholders(
    value: Any,
    *,
    path: str,
    feature: str,
    missing: str,
    out: list[dict[str, Any]],
) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_path = f"{path}.{key}"
            if isinstance(key, str):
                for match in _PLACEHOLDER_RE.findall(key):
                    out.append({"feature": feature, "missing": missing, "path": key_path, "value": match})
            _collect_placeholders(nested, path=key_path, feature=feature, missing=missing, out=out)
        return
    if isinstance(value, list):
        for index, nested in enumerate(value):
            _collect_placeholders(nested, path=f"{path}[{index}]", feature=feature, missing=missing, out=out)
        return
    if isinstance(value, str):
        for match in _PLACEHOLDER_RE.findall(value):
            out.append({"feature": feature, "missing": missing, "path": path, "value": match})
