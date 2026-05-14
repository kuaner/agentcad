# ADR: Section Package Boundaries

Date: 2026-05-14

## Context

`src/agentcad/section.py` was 823 lines. Unlike earlier contract and suggest
work, the problem was not a workflow reverse dependency. The module was still a
cohesive low-level section-analysis layer, but it combined several stable
responsibilities that agents frequently need to inspect when planning probes and
checks:

- triangle-plane section extraction;
- profile scans and component analysis;
- ad-hoc region, line, and point measurements;
- SVG rendering and sidecar JSON writing;
- per-validation section caching.

Keeping all of that in one file made LLM reads expensive and encouraged future
section features to pile into the same surface.

## Decision

Keep the public `agentcad.section` API compatible, but make it a package:

- `section/types.py`: axis constants and `Segment2D`.
- `section/extraction.py`: `section_segments` and triangle-plane intersection
  helpers.
- `section/analysis.py`: `scan_profile` and `analyze_section_segments`.
- `section/measure.py`: `query_section_measurements` and region/line/point
  measurement helpers.
- `section/render.py`: `render_section_svg`, `write_section_svg`, and SVG
  helpers.
- `section/cache.py`: `SectionCache`.

The root package re-exports the historical public API, including `_empty_svg`
for existing tests and callers.

## Guardrails

`tests/test_architecture.py` now enforces:

- `src/agentcad/section.py` must not return.
- Section submodules stay under explicit line ceilings.
- Section internals do not import workflow frontends.
