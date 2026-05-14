# ADR: Probe Subsystem Refactor

Date: 2026-05-14

## Context

`src/agentcad/probe.py` grew to roughly 1200 lines and mixed three different
responsibilities:

- planning high-information probe commands from design intent, checks,
  metadata, validation, and failure modes;
- executing planned probes against STL section geometry;
- exposing the workflow command that reads/writes model artifacts.

This created an avoidable dependency: `suggest-checks` only needs the planner,
but importing `agentcad.probe` also loaded execution code.

## Decision

Turn `agentcad.probe` into a package while preserving public imports:

```python
from agentcad.probe import plan_probes, plan_probe_points, probe_model, probe_scan
```

The package is split by responsibility:

```text
agentcad/probe/
  __init__.py      public compatibility exports
  core.py          plan_probes workflow and probes.json artifact writing
  planner.py       pure probe suggestion planning
  execution.py     probe_model, probe_scan, run_probe_plan
  utils.py         small parsing/formatting helpers shared by planner/execution
```

`suggest/core.py` imports `agentcad.probe.planner` directly so check suggestion
does not depend on probe execution.

## Constraints

- Keep CLI behavior and JSON payload schemas stable.
- Keep `agentcad.probe` import-compatible for downstream code.
- Keep the planner pure: no STL reads, no workspace writes, no CLI imports.
- Execution may depend on STL/section utilities, but not on suggest/review/CLI.

## Acceptance

- `uv run pytest tests/test_probe.py tests/test_suggest.py tests/test_cli.py -q`
- `uv run pytest tests/test_architecture.py -q`
- Final phase: `uv run pytest -q`
