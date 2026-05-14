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
- `contract/common.py`: shared evidence constants, feature classifiers, and
  schema issue primitives.
- `contract/schema.py`: `design.json` schema validation and project/name design
  loading wrappers.
- `contract/evidence.py`: feature coverage, feature evidence matrix, and design
  intent lint policy.
- `contract/weak.py`: weak-check warnings for under-specified mechanical
  features.
- `contract/params.py`: small parameter-name search helper used by suggested
  fixes.
- `suggest/core.py`: `suggest-checks` workflow orchestration and payload shape.
- `suggest/templates.py`: check-template selection and construction.
- `suggest/facts.py`: feature/metadata/check fact extraction for template
  grounding.
- `suggest/geometry.py`: geometry/params fallback helpers used by suggestion
  templates.
- `suggest/types.py`: shared suggestion context types.
- `section.py`: lower-level STL section extraction, measurement, and SVG output.
  Split only when adding a second rendering format or a new family of section
  queries; today its callers share the same section-analysis abstraction.

## Executable Rules

`tests/test_architecture.py` enforces:

- `agentcad.assembly` remains a package; `src/agentcad/assembly.py` must not
  return.
- Public assembly entry points stay re-exported through `agentcad.assembly`.
- Assembly internals must not import CLI, batch, model review, suggest, probe,
  doctor, or snapshot modules.
- `agentcad.contract` remains a package; `src/agentcad/contract.py` must not
  return.
- Contract internals must not import workflow frontends such as CLI, validate,
  review, suggest, probe, assembly, render, or preview.
- Workflow modules that need contract policy import the specific contract
  submodule (`contract.schema`, `contract.evidence`, `contract.weak`,
  `contract.common`, or `contract.params`) instead of the contract root.
- `agentcad.suggest` remains a package; `src/agentcad/suggest.py` must not
  return.
- `suggest/core.py` must import `agentcad.probe.planner`, not the probe package or
  execution layer.
- Hot files have explicit line ceilings so growth is intentional.
- Generated files are not tracked by git.
