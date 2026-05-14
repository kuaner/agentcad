# Architecture Guardrails

Date: 2026-05-14

## Purpose

AgentCAD changes quickly because agents add features, probes, checks, examples,
and review gates in the same flow. The main architectural risk is not one bad
function; it is letting unrelated responsibilities collect in one convenient
module until every later change becomes risky.

The guardrails below keep the codebase easy to extend without premature
frameworks.

## Principles

1. Public workflow modules orchestrate; domain modules decide.
2. A package boundary is justified when a feature has multiple stable
   responsibilities, not simply because a file is long.
3. JSON schemas and CLI payload shapes are contracts. Move code mechanically
   first; change behavior in separate, tested commits.
4. Generated files are not source. `__pycache__`, `.pyc`, `.DS_Store`, and
   validation outputs must remain ignored and untracked.
5. Line ceilings are tripwires, not style rules. If a file hits a ceiling,
   either extract a responsibility or update this document with a concrete
   reason.

## Current Boundaries

- `assembly/core.py`: orchestration for init/list/measure/validate only.
- `assembly/checks.py`: assembly check evaluation and interface contract gates.
- `assembly/references.py`: metadata reference resolution and descriptor
  transforms.
- `assembly/mates.py`: measurable mate residuals.
- `assembly/artifacts.py`: preview/STL/MJCF artifact generation.
- `probe/core.py`: probe-plan workflow orchestration and artifact writing.
- `probe/planner.py`: pure probe suggestion planning used by both `probe --plan`
  and `suggest-checks`.
- `probe/execution.py`: STL section probing and execution of planned probes.
- `contract.py`: schema and review-gate policy. Split only around stable schema
  groups, not individual validators.

## Executable Rules

`tests/test_architecture.py` enforces:

- `agentcad.assembly` remains a package; `src/agentcad/assembly.py` must not
  return.
- Public assembly entry points stay re-exported through `agentcad.assembly`.
- Assembly internals must not import CLI, batch, model review, suggest, probe,
  doctor, or snapshot modules.
- `suggest.py` must import `agentcad.probe.planner`, not the probe package or
  execution layer.
- Hot files have explicit line ceilings so growth is intentional.
- Generated files are not tracked by git.
