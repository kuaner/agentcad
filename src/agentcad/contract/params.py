from __future__ import annotations

def search_params_by_keywords(params: dict, keywords: frozenset | set, max_results: int = 3) -> list[str]:
    """Search params.json keys matching keywords and return matching key names."""
    if not isinstance(params, dict):
        return []
    candidates: list[str] = []
    for key in sorted(params.keys()):
        key_lower = str(key).lower()
        if any(kw in key_lower for kw in keywords):
            candidates.append(str(key))
    return candidates[:max_results]
