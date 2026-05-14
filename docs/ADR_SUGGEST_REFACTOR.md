# ADR: Suggest-Checks Package Boundaries

Date: 2026-05-14

## Context

`src/agentcad/suggest.py` directly affects how agents choose checks before
model delivery. It had four different responsibilities in one file:

- loading `design.json`, artifacts, evidence matrix, and probe plans;
- choosing which missing evidence to suggest;
- extracting hole/interface facts from metadata and linked checks;
- building concrete check templates from params, geometry, and fallbacks.

That made future check-suggestion work likely to mix orchestration, facts, and
template construction.

## Decision

Keep `agentcad.suggest.suggest_checks` compatible, but make `suggest` a package:

- `suggest/core.py`: workflow orchestration and output payload.
- `suggest/templates.py`: check-template construction and evidence-matrix
  suggestion expansion.
- `suggest/facts.py`: feature, metadata, and linked-check fact extraction.
- `suggest/geometry.py`: bbox, axis/range, tolerance, and parameter fallback
  helpers.
- `suggest/types.py`: shared `SuggestContext`.

The core continues to use `probe.planner` for high-information probe points.
Template and fact modules depend on contract submodules directly, not on the
contract root package.

## Guardrails

`tests/test_architecture.py` now enforces:

- `src/agentcad/suggest.py` must not return.
- `suggest/core.py` depends on `agentcad.probe.planner`, not the probe package
  root or execution layer.
- Suggest submodules stay under explicit line ceilings.
