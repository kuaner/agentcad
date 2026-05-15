from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

DOC_PATHS = [
    ROOT / "README.md",
    ROOT / "CLAUDE.md",
    ROOT / "src" / "agentcad" / "_templates" / "workspace" / "CLAUDE.md",
    ROOT / "src" / "agentcad" / "_templates" / "model" / "README.md",
    ROOT / "src" / "agentcad" / "_templates" / "workspace" / "references" / "validation-strategy.md",
    ROOT / "examples" / "workflow-proof-wall-hook" / "CLAUDE.md",
]

BANNED_PREVIEW_TEXT = ["--static", "offline HTML", "stlBase64"]


def test_preview_docs_do_not_regress_to_static_or_embedded_modes():
    offenders = []
    for path in DOC_PATHS:
        text = path.read_text(encoding="utf-8")
        for needle in BANNED_PREVIEW_TEXT:
            if needle in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {needle!r}")

    assert offenders == []


def test_primary_docs_reference_workflow_gate():
    for path in DOC_PATHS[:4]:
        assert "agentcad workflow" in path.read_text(encoding="utf-8")
