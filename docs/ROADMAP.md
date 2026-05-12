# AgentCAD Roadmap

Last updated: 2026-05-12

This document is the actionable companion to [`DESIGN.md`](DESIGN.md). It
takes the high-level milestones (V0 – V6) and breaks them into concrete,
sequenced engineering tasks with explicit acceptance criteria. The
ordering reflects current priorities; stages are independent enough that
ordering can be revisited at the start of each milestone.

For background on what is already shipped, see
[`STATUS.md`](STATUS.md).

## Milestone overview

| Milestone | Theme | Status | Headline outcome |
|---|---|---|---|
| V0 | Minimal agent loop | ✅ delivered | new / build / measure / render / validate / deliver |
| V1 | Geometry observability | ✅ delivered | three-axis probe + scan, multi-view, debug SVGs |
| V2 | Design spec standardization | ✅ delivered | check IDs, schema, weak-check warnings, Markdown report |
| V2.5 | Design-time observability | ✅ delivered | `precheck`, `review`, four relational checks, common-error catalog |
| V3 | Feature library | ✅ delivered | `agentcad.features`, `ContractBuilder`, hardware tables, helper-driven examples |
| V4 | Assembly + relations | ✅ delivered | assembly contracts, mate residuals, fit checks, mesh narrow phase, interactive preview, mandatory MJCF |
| **V5** | **CAD CI** | **partially delivered / next** | **fast/slow GitHub Actions exist; `validate all`, regression snapshots, benchmarks remain** |
| V6 | Optional integrations | deferred | MCP server, PNG / glTF previews, external viewer handoff |

## V3 — Feature library

Status: delivered in `agentcad.features`.

### Why it was needed

Across the existing examples we already see the same primitives written
by hand multiple times:

- the fan-adapter has a 71.5 mm bolt pattern;
- the magnetic outlet plate has the same pattern plus stepped bores;
- the mounting bracket repeats two M4 through-holes;
- the iPhone case has rounded plates with multiple rectangular cutouts.

Every one of these required the agent to write the geometry **and** to
write the matching checks (`bbox_size`, `inner_diameter_at_z`,
`min_clearance`, `hole_accessibility`). The check side is mechanical and
prone to omission. Helpers write both halves at once.

### Delivered scope

Exposed as a thin `agentcad.features` module that returns build123d objects
and can register matching feature/check records through `ContractBuilder`.

Delivered helper set:

| Helper group | Helpers |
|---|---|
| base and masks | `plate`, `boss`, `rib`, `slot`, `tube`, `rect_tube`, `prismoid`, `wedge`, `torus`, `pie_slice`, `chamfer_mask`, `rounding_mask` |
| holes and hardware | `mounting_pattern`, `screw_hole`, `stepped_bore`, `nut_trap`, `nut_body`, `screw`, `threaded_rod`, `threaded_nut`, `sinusoidal_thread` |
| mechanisms and patterns | `duct_socket`, `living_hinge_mask`, `dovetail`, `hex_panel`, `snap_pin`, `snap_pin_socket`, `sparse_wall`, `nema_mount` |
| gears and surfaces | `spur_gear`, `ring_gear`, `helical_knurl` |

Each helper:

- accepts a `name` argument that becomes both the build123d label and
  the `feature_id` in `design.json`;
- can register feature/check entries into a supplied `ContractBuilder`;
- emits checks appropriate to the helper class, such as bbox, diameter,
  section, wall-thickness, volume, or feature-position checks;
- composes with `agentcad.hardware` lookup tables for screws, nuts, washers,
  and heat-set inserts where relevant.

### Delivered artifacts

1. `src/agentcad/features/` — public helper modules plus shared geometry code.
2. `src/agentcad/features/contract.py` — `ContractBuilder` merge/write support.
3. `src/agentcad/hardware/` — hardware dimension database.
4. `tests/test_features/` — helper coverage per module.
5. Helper-driven examples: `e2e-feature-demo`, `e2e-feature-helpers`,
   `drone-panel`, `gear-housing`, and `pipe-coupling`.
6. Workspace reference templates include feature usage notes under
   `references/feature/`.

### Acceptance status

- 30+ helpers ship with focused tests.
- `ContractBuilder` writes/merges helper records into `design.json` and avoids
  duplicate scaffold entries.
- Helper-driven workspaces exercise real model generation and validation.
- The feature layer remains Python-first; a declarative DSL is still deferred.

### Follow-up questions

- Should more helpers emit structured metadata for assembly interfaces?
- Which repeated helper combinations deserve composite helpers, and which
  should stay explicit in `part.py`?

---

## V4 — Assembly + relations

Detailed design proposal: [`ASSEMBLY_TECHNICAL_PLAN.md`](ASSEMBLY_TECHNICAL_PLAN.md).

Status: V4 validation is delivered in the CLI as
`agentcad assembly init/list/validate/review` plus the cross-cutting
`agentcad preview <name>` command for both models and assemblies. The delivered
workflow includes mesh narrow-phase interference evidence, descriptor-based
inter-model clearance, assembly section component counts, combined STL export,
MJCF round-trip validation, and a `fan_with_screen` acceptance fixture.

### Why

V3 makes single parts cheap to author. The next ceiling was multi-part
assemblies: most real CAD work is "this part bolts to that part with X
clearance and Y mate". V4 gives the agent a shared assembly coordinate system,
explicit mate/clearance contracts, and generated evidence instead of forcing it
to compare unrelated model outputs manually. The
`examples/e2e-bit-holder/` body/lid test remains the regression fixture for
that workflow.

### Scope

- `cadproject.json` gains an optional `assemblies:` array. Each
  assembly references models by name, supplies a transform per model,
  and a list of mate points.
- New CLI:
  - `agentcad assembly init <name>` — scaffold an assembly directory.
  - `agentcad assembly list` — list discovered assemblies.
  - `agentcad assembly validate <name>` — run inter-model
    checks, emit combined/exploded SVG previews, generate an explodable
    component-isolation `preview.html`, and generate MJCF.
  - `agentcad preview <name>` — regenerate the local interactive Three.js
    review page for either a model or an assembly. Preview is a universal
    artifact-viewing command; assembly is optional and should not own it.
  - `agentcad assembly review <name>` — block delivery on uncovered mates,
    missing MJCF, stale artifacts, or unresolved component-pair risks.
- Inter-model relational checks: the existing four geometric-relation
  checks gain a `feature_a_model` / `feature_b_model` syntax so they can
  reference shapes declared in two different models.
- Metadata-to-geometry consistency checks ensure assembly interfaces declared in
  `metadata.json` match the built STL instead of being trusted blindly.
- Mandatory MJCF export as a human-verifiable assembly artifact. Optional
  MuJoCo-derived metrics may augment external viewer workflows, but do not
  replace AgentCAD's numeric checks.

### Acceptance

- `examples/fan-adapter-8025/assemblies/fan_with_screen/` combines the existing
  `fan_duct_adapter_8025` and `outlet_magnetic_screen_plate_8025` models into
  an assembly that passes descriptor clearance, mesh penetration,
  section-count, bbox, MJCF, and preview artifact checks.

---

## V5 — CAD CI

Delivered:

- `.github/workflows/ci.yml` runs the fast test suite on pushes and pull
  requests, plus a CLI entrypoint smoke test.
- `.github/workflows/slow-tests.yml` runs slow tests on a daily schedule and
  manual trigger.
- `.github/workflows/publish.yml` verifies via CI before building and
  publishing tagged releases to PyPI.

Remaining:

- `agentcad validate all` walks every model in the workspace.
- Regression snapshots hash STEP / STL outputs and store `validation.json`;
  PRs that change either are flagged.
- Benchmark suite tracks build time, validation time, and mesh size per
  example.
- Optional batch model generation for example and fixture workspaces.

### Acceptance

- A red-vs-green PR demo where a helper change causes one example's
  mesh hash to drift; CI flags the regression and the diff is
  human-reviewable.

---

## V6 — Optional integrations (deferred)

Kept out of the core loop on purpose. Pick up only when the CLI
+ JSON contract is no longer enough.

- MCP server exposing the same CLI surface (so non-CLI agents can
  drive AgentCAD).
- PNG / glTF / STEP-AP242 export.
- External viewer handoff beyond the generated HTML preview.
- Template gallery (browse-and-fork existing models).

---

## Cross-cutting tasks (any milestone)

These are smaller items that can be done at any point; group them into
PRs alongside whichever milestone they support.

- **Section semantics**: today's `section_bbox_at_z` `expected: "void"`
  treats any empty intersection as a void. Tighten by requiring the
  `region` argument when the model is hollow, so a missed mesh
  slice does not silently pass.
- **Probe ergonomics follow-up**: `--cx` / `--cy` aliases are delivered for
  radial centers. Continue smoothing multi-plane probe input if more CLI
  parsing traps appear.
- **Render speed**: section SVG rendering on the iPhone case takes
  >1 s; profile and cache the triangle-plane intersection.
- **`agentcad sync` refinements**: `--dry-run`, `--only`, and
  `--prune-deprecated` are delivered. Future work can add richer diff output if
  template churn grows.
- **`min_wall_thickness` 3D mode**: today the check works on a single Z
  slice. Extend with a Z-range option that takes the worst slice.
- **Common-error regression tests**: each catalogued common error
  (hole-wall interference, hole-edge break, hole-to-hole, rib blocking
  bolt) gets a fixture model that *should* fail validation, plus a
  test that asserts validation fails for the right reason.

---

## Decision log (recent)

| Date | Decision | Why |
|---|---|---|
| 2026-05-12 | Treat V3 helper library as delivered and keep it Python-first | The merged `agentcad.features` surface and tests cover the repeated primitive problem without needing a declarative DSL. |
| 2026-05-12 | Split CI into fast, slow, and publish workflows | Fast feedback should run on every push/PR, while slow CAD-heavy tests and release publishing need separate triggers. |
| 2026-05-07 | Treat the four geometric-relation checks as design-time first, post-build second | The original interference bug was a hand-math error in `design.json`; catching it post-build is too late and re-runs cost agent context. |
| 2026-05-07 | Make `precheck` and `review` mandatory checkpoints | The mounting-bracket E2E run only surfaced the hole-wall interference because we manually inspected the iso preview. Reviewing must be cheap and routine. |
| 2026-05-07 | All workspace docs are English-only | Mixed-language templates were confusing for agents that translate selectively; English is the lingua franca. |
| 2026-05-06 | Helpers (V3) over a declarative DSL | A DSL forces upfront design choices we have not learned yet; helpers compose freely and emit matching checks today. |
| 2026-05-06 | No project-root `outputs/` directory | Each model owns its artifacts; ambiguity caused stale-artifact bugs in early V0. |

---

## How to keep this document accurate

- After every milestone PR, update the table in
  [Milestone overview](#milestone-overview) and the corresponding
  STATUS.md milestone block.
- Add a row to the [Decision log](#decision-log-recent) whenever a
  major roadmap question is settled.
- Open questions for an in-flight milestone live under that milestone's
  "Open questions" subsection, not in the global section.
