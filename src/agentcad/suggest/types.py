from __future__ import annotations

from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class SuggestContext:
    params: dict[str, Any]
    metadata: dict[str, Any]
    geometry: dict[str, Any]
    validation: dict[str, Any]
    observability: dict[str, Any]
    feature_evidence_matrix: list[dict[str, Any]]
    probe_plan: list[dict[str, Any]]
