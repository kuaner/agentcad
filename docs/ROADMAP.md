# AgentCAD Roadmap

Last updated: 2026-05-12

This roadmap is intentionally forward-looking. Historical delivery details live
in [`STATUS.md`](STATUS.md); this document answers what should be built next,
why it matters, and how to know each step is done.

Detailed PR-level execution plans, module ownership, payload sketches, and test
matrices live in [`ROADMAP_EXECUTION_PLAN.md`](ROADMAP_EXECUTION_PLAN.md).

## Current Position

AgentCAD already has a strong single-model and early assembly loop:

- workspace scaffolding, model variants, sync, build, measure, render, preview,
  validate, diff, review, report, and deliver
- design-time precheck with relational geometry checks
- post-build mesh, section, volume, artifact, metadata, and feature coverage
  checks
- a broad `agentcad.features` helper library backed by hardware dimension
  tables
- first-class assembly validation with transforms, mates, clearance,
  interference evidence, MJCF export, and interactive preview
- fast/slow GitHub Actions workflows and PyPI publishing

The biggest remaining gap is not "more CAD primitives". The useful next step is
to make AgentCAD reliable at project scale: every example and workspace should
be batch-validatable, regressions should be reviewable in CI, contracts should
be harder to write incorrectly, and agents should get clearer feedback when a
model is valid but mechanically weak.

## Roadmap Principles

1. **Evidence before export**: STEP/STL/preview artifacts are deliverables only
   after contracts, measurements, and review gates agree.
2. **Batch reliability beats more demos**: one-off examples are useful only when
   they become repeatable regression fixtures.
3. **Contracts must get stricter over time**: ambiguous checks that can pass for
   the wrong reason should become warnings first, then failures.
4. **Helpers are not a DSL yet**: keep the feature layer Python-first until
   repeated composition problems justify a declarative schema.
5. **Integrations come after invariants**: MCP, glTF, and richer viewers should
   not arrive before validation, regression, and schema guarantees are solid.

## Priority Map

| Priority | Theme | Status | Primary outcome |
|---|---|---|---|
| P0 | Batch validation and regression CI | Next | `agentcad validate all` plus reviewable geometry/check drift |
| P1 | Contract and schema hardening | Next | Fewer false passes and clearer machine-readable contract errors |
| P2 | Assembly productization | Next | Assemblies move from working feature to trusted product workflow |
| P3 | Agent authoring UX | Next | Agents need fewer manual probes and write stronger checks by default |
| P4 | Performance and artifact hygiene | Opportunistic | Faster section/render/validation runs with cleaner outputs |
| P5 | Optional integrations | Deferred | MCP and extra export formats after CLI invariants are stable |

---

## P0 — Batch Validation And Regression CI

### Why

The project now has enough examples, helpers, and assembly fixtures that manual
validation is no longer a good safety net. A change to a helper, section
analysis, STL parsing, or preview generation can silently affect many models.
The next valuable milestone is a workspace-scale validation command and CI
evidence that makes those changes reviewable.

### Scope

- Add `agentcad validate all` for workspace-level validation.
- Discover models, variants, and assemblies from `cadproject.json` and the
  filesystem.
- Support filters such as `--models`, `--assemblies`, `--changed-only`,
  `--include-slow`, and `--fail-fast`.
- Emit a project-level report under `outputs/` or `.agentcad/` without creating
  ambiguous model artifacts.
- Store normalized validation snapshots for selected examples.
- Compare current results against snapshots:
  - check status drift
  - bbox, volume, triangle count, and section metric drift
  - STEP/STL hash drift where hash stability is expected
  - preview/MJCF artifact presence
- Add a CI workflow step that runs batch validation on representative fixtures.

### Acceptance

- `agentcad validate all` returns stable JSON with totals, per-target status,
  artifact paths, and a nonzero exit code on failure.
- The command validates normal models, model variants, and assemblies in one
  workspace.
- At least `fan-adapter-8025`, `e2e-bit-holder`, `e2e-feature-helpers`,
  `drone-panel`, `gear-housing`, and `pipe-coupling` are covered by a batch
  fixture.
- A deliberate helper geometry change produces a CI-readable regression report
  rather than only a failing test name.

### Out Of Scope

- Cloud artifact storage.
- Full visual snapshot testing.
- Guaranteeing byte-identical STEP output across all platforms.

---

## P1 — Contract And Schema Hardening

### Why

The contract layer is now central to correctness, but several checks can still
be underspecified. The next hardening pass should reduce false passes and make
invalid contracts fail with precise, actionable errors before any geometry is
built.

### Scope

- Formalize schemas for:
  - `design.json`
  - `metadata.json`
  - `assembly.json`
  - validation and review output payloads
- Add schema-version migration rules or explicit unsupported-version errors.
- Tighten `section_bbox_at_z` semantics:
  - require `region` for hollow or void assertions that could pass on an empty
    slice
  - distinguish "no mesh at this plane" from "expected void in this region"
- Extend `min_wall_thickness` from a single plane to a Z-range / axis-range mode
  that reports the worst slice.
- Add negative regression fixtures for known failures:
  - hole-wall interference
  - hole-to-edge break
  - hole-to-hole pitch too tight
  - shallow through-hole
  - rib or boss blocking tool access
  - detached lip/tab/rib that passes body-exists checks
- Make weak-check warnings more specific:
  - "feature has only envelope checks"
  - "hole lacks access check"
  - "load-bearing attachment lacks root/interface check"
  - "assembly interface declared in metadata but not measured"

### Acceptance

- Invalid contracts fail in `precheck` with field-level error paths.
- Every known common-error fixture fails for the intended reason.
- The weak-check report can be used by an agent to add a better check without
  reverse-engineering the validator.
- No existing valid example becomes red without a documented migration note.

---

## P2 — Assembly Productization

### Why

Assembly validation exists and is valuable, but it should become easier to trust
for real multi-part products. The project needs stricter metadata contracts,
better assembly examples, and clearer review gates before assembly is treated as
mature as single-part validation.

### Scope

- Define an assembly-ready `metadata.json` schema for anchors and interfaces.
- Add helper support for emitting common interfaces:
  - cylindrical male/female sockets
  - screw axes and install envelopes
  - snap-fit pin/socket pairs
  - dovetail rails
  - gear axes and pitch references
- Add assembly fixtures beyond `fan_with_screen`:
  - body/lid fit fixture
  - snap-fit fixture
  - gear housing fixture
  - fastened plate fixture
- Expand assembly review:
  - uncovered component pair risks
  - missing interface measurement
  - stale component artifact detection
  - missing preview/MJCF/combined STL artifacts
- Evaluate whether exact STEP assembly export is necessary; keep combined STL
  plus MJCF as the default until a concrete downstream workflow needs STEP
  assembly.

### Acceptance

- New assembly fixtures fail when a mate, clearance, or transform is
  intentionally wrong.
- Assembly review blocks delivery on missing interface evidence, not just
  malformed JSON.
- Helper-emitted interfaces can be consumed by assembly validation without
  hand-copying metadata coordinates.
- MJCF round-trip checks remain supplemental evidence, not the source of truth.

---

## P3 — Agent Authoring UX

### Why

AgentCAD is agent-first, so the most valuable UX work is not a desktop UI. It
is reducing the number of manual reasoning steps an agent needs to create a
strong contract and debug a failing model.

### Scope

- Add `agentcad doctor <model>` or extend `review` with a stronger advisory
  mode:
  - missing checks by feature type
  - likely better probe commands
  - stale or contradictory artifacts
  - weak helper usage patterns
- Add `agentcad suggest-checks <model>` based on `features`, `params.json`,
  helper metadata, and existing probes.
- Improve `suggested_fix` payloads:
  - include parameter candidates when `param_ref` is absent but likely
  - distinguish "contract likely wrong" from "geometry likely wrong"
  - include the exact probe/render commands to verify a fix
- Add a helper cookbook generated from tested snippets, not prose-only docs.
- Make template sync safer for long-lived projects:
  - richer `sync --dry-run` diff output
  - conflict markers or side-by-side paths for locally modified templates

### Acceptance

- A fresh agent can take a scaffolded non-trivial part from concept to review
  with fewer manual probe guesses.
- Failing validation output names the next command to run for the top common
  failure classes.
- Helper docs include executable snippets covered by tests.
- `sync --dry-run` is useful enough to review template drift before writing.

---

## P4 — Performance And Artifact Hygiene

### Why

As batch validation grows, slow section extraction and noisy artifacts will
become development friction. Performance work should be targeted at measured
hot spots, not speculative rewrites.

### Scope

- Profile section extraction on complex examples such as `iphone15pro-case`.
- Cache triangle-plane intersections where repeated section checks share an
  axis or nearby plane.
- Add timing data to validation output:
  - build time
  - measure time
  - render time
  - check time
  - preview generation time
- Define artifact retention rules:
  - validation history count / age
  - debug SVG cleanup
  - preview regeneration policy
- Add benchmark reporting for representative examples in slow CI.

### Acceptance

- Batch validation reports per-target timing and identifies slow stages.
- Section-heavy examples get a measurable speedup without changing validation
  semantics.
- Generated artifacts are predictable enough for CI and local cleanup.

---

## P5 — Optional Integrations

### Why

Integrations are useful only after the CLI contract is stable. Until then, they
risk multiplying unstable surfaces.

### Candidate Work

- MCP server exposing the same validated CLI operations.
- PNG snapshots for CI comments and release artifacts.
- glTF export or viewer handoff for workflows where STL + SVG + HTML preview is
  not enough.
- Template gallery for browse-and-fork example workspaces.
- STEP-AP242 or richer CAD exchange export if downstream CAD tools require it.

### Entry Criteria

- `validate all` and regression snapshots are working.
- Schemas are explicit enough that external clients do not need to infer
  payload shape.
- At least one real external workflow requires the integration.

---

## Near-Term Execution Plan

### Next PR: `agentcad validate all`

1. Add target discovery for models, variants, and assemblies.
2. Run validation/review in a deterministic order.
3. Emit a project-level JSON summary.
4. Cover discovery and failure behavior in tests.
5. Add one example workspace batch fixture.

### Following PR: regression snapshots

1. Define normalized snapshot format.
2. Add `agentcad diff --snapshot` or a dedicated snapshot compare command.
3. Store snapshots for selected examples.
4. Wire snapshot comparison into CI for representative fixtures.

### Following PR: contract hardening fixtures

1. Add negative fixture models for the common-error catalog.
2. Assert each fixture fails for the intended check type.
3. Promote the most reliable weak-check warnings into blocking review gates.

## Decision Log

| Date | Decision | Why |
|---|---|---|
| 2026-05-12 | Make batch validation and regression CI the next priority | The project now has enough examples and helpers that manual per-model validation is the main reliability bottleneck. |
| 2026-05-12 | Treat V3 helper library as delivered and keep it Python-first | The merged `agentcad.features` surface and tests solve repeated primitive authoring without needing a declarative DSL. |
| 2026-05-12 | Split CI into fast, slow, and publish workflows | Fast feedback should run on every push/PR, while CAD-heavy tests and release publishing need separate triggers. |
| 2026-05-07 | Treat geometric-relation checks as design-time first, post-build second | The original interference bug was a hand-math error in `design.json`; catching it post-build is too late. |
| 2026-05-07 | Make `precheck` and `review` mandatory checkpoints | Hole-wall interference and floating-feature failures need cheap routine gates, not occasional human inspection. |
| 2026-05-07 | Keep workspace docs English-only | Mixed-language templates were confusing for agents that translate selectively. |
| 2026-05-06 | Keep helpers over a declarative DSL for now | Python helpers compose freely while the correct higher-level schema is still unclear. |
| 2026-05-06 | Avoid project-root model outputs | Each model owns its artifacts; ambiguous root outputs caused stale-artifact bugs early on. |

## Keeping This Roadmap Useful

- Move completed work to [`STATUS.md`](STATUS.md); keep this file focused on
  decisions still ahead.
- Add acceptance criteria before starting implementation.
- Remove or demote items that do not protect correctness, repeatability, or
  agent autonomy.
- Re-rank priorities after every real e2e modeling session.
