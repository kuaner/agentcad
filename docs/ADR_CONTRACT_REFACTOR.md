# ADR: Contract Package Boundaries

Date: 2026-05-14

## Context

`src/agentcad/contract.py` had become the central policy module for schema
validation, feature classification, feature evidence matrix gates, design-intent
lint, weak-check warnings, and parameter hint lookup. That made every new
modeling-policy change land in the same file, even when the behavior belonged
to separate stages of the agent workflow.

The risk was not only file length. The real problem was unclear ownership:
schema rules, evidence rules, and weak-check policy change for different
reasons but were stored as one module.

## Decision

Keep the public `agentcad.contract` API compatible, but make it a package with
explicit internal responsibilities:

- `contract/common.py`: shared constants, `SchemaIssue`, `_issue`, feature
  classification, and normalized design-intent helpers.
- `contract/schema.py`: design schema validation plus project/name
  `design.json` loading wrappers.
- `contract/evidence.py`: feature coverage, feature evidence matrix, and
  design-intent lint policy.
- `contract/weak.py`: weak-check warnings for under-specified mechanical
  features.
- `contract/params.py`: parameter-name search used by suggested fixes.

Internal workflow modules now import these submodules directly. The root package
exists for backwards-compatible external imports and tests.

## Non-Decision

`section.py` is still a single module. It is large, but it remains a cohesive
lower-level section-analysis abstraction with no workflow reverse dependency.
Split it when a new rendering format or a new family of query APIs creates a
stable second responsibility.

## Guardrails

`tests/test_architecture.py` now enforces:

- `src/agentcad/contract.py` must not return.
- Contract submodules stay under explicit line ceilings.
- Contract internals do not import workflow frontends.
- Workflow modules import contract submodules directly rather than the contract
  root.
