# AgentCAD

[![PyPI](https://img.shields.io/pypi/v/agentcad-cli.svg)](https://pypi.org/project/agentcad-cli/)

AgentCAD is a CLI-first CAD workflow runtime for coding agents.

It gives a coding agent a repeatable workspace, a contract-driven modeling
protocol, deterministic build/export, geometric measurement, multi-view
previews, design-time and post-build validation, regression snapshots,
assembly validation, workflow diagnostics, and a delivery manifest —
so the agent can iterate on CAD models with measurable feedback instead of
visual intuition.

```text
discovery -> concept -> design contract -> suggest-checks -> precheck
  -> params/source -> build -> measure -> render -> validate
  -> review -> quality review -> preview -> deliver
```

If interrupted at any stage, `agentcad doctor <model>` reports workflow gaps
and recommends the next command.

## What's in the box

| Stage | Command | Purpose |
|---|---|---|
| Init | `agentcad init <workspace> [--model <name>]` | Initialize workspace scaffold (optionally create first model) |
| Scaffold | `agentcad new <model>` | Create model folder inside an existing workspace |
| Scaffold | `agentcad new <model>:<variant>` | Create a variant (same `part.py`, different `params.json`) |
| Sync | `agentcad sync [--dry-run] [--only <path>] [--prune-deprecated]` | Refresh workspace scaffold from latest templates, preview changes, or prune deprecated scaffold paths |
| Suggest | `agentcad suggest-checks <model>` | Analyze design contract and recommend missing concrete checks by feature classification, evidence gaps, existing artifacts, and probe plan |
| Precheck | `agentcad precheck <model>` | Solve `design.json` statically (schema, feature coverage, `min_clearance`) **before** part.py is written |
| Build | `agentcad build <model>[:<variant>]` | Run `part.py` through build123d, export STEP + STL, hash-cache stale runs |
| Measure | `agentcad measure <model>[:<variant>]` | Mesh stats + structural facts (bbox, watertight, triangles, voids) |
| Render | `agentcad render <model>` | Iso/front/top/side/back SVG previews with dimension annotations + Z/X/Y cross-section SVGs with measurement sidecars |
| Preview | `agentcad preview <name>[:<variant>]` | Interactive Three.js preview for models and assemblies served through a local HTTP server |
| Probe | `agentcad probe <model>` | Cross-section diameter / bbox / component analysis plus ad-hoc line, point, and region measurements; `--scan` to discover step changes; `--cx/--cy` avoid negative-number parsing issues |
| Inspect | `agentcad inspect <model>` | Three-axis scan + automatic section SVGs + measurement JSON + suggested probes |
| Validate | `agentcad validate <model>[:<variant>]` | Build + measure + render all orthographic previews + design checks + feature coverage + fix suggestions (includes timing and section cache) |
| Validate all | `agentcad validate all [--models] [--assemblies] [--include-variants] [--fail-fast]` | Batch validate all workspace targets with project-level report |
| Snapshot | `agentcad snapshot write [--target <name>]` | Write regression snapshots for validated targets |
| Snapshot | `agentcad snapshot compare [--target <name>]` | Compare current vs baseline snapshots (check drift, geometry drift, artifact changes) |
| Diff | `agentcad diff <model> [--last]` | Compare current vs previous validation run: fixed/regressed/stable checks + geometry drift |
| Doctor | `agentcad doctor <model>[:<variant>]` | Workflow state diagnostics: severity-graded findings and recommended next command |
| Review | `agentcad review <model>` | Pre-delivery checklist with pairwise relations matrix, hole-access enforcement, weak-check blocking gates, and must-view SVG list |
| Clean | `agentcad clean [--model <name>] [--dry-run] [--no-validation-history] [--no-debug] [--previews]` | Remove debug SVGs, old validation history, optionally preview SVGs |
| Assembly | `agentcad assembly init/list/validate/review` | Optional multi-model assembly contracts with component transforms, mate residuals, fit checks, combined/exploded SVGs, preview generation, MJCF export, and metadata interface validation |
| Deliver | `agentcad deliver <model>[:<variant>]` | Delivery manifest |
| Report | `agentcad report <model>` | Markdown summary of validation result |
| CADBench | `agentcad cadbench [--root examples/cadbench]` | Evaluate contract-only failure-mode fixtures for evidence coverage, suggestion specificity, placeholder budgets, and probe relevance |

Every command prints stable machine-readable JSON output. Failures include
`stage`, `error.type`, and `error.message`. Validation failures include
`suggested_fix` with `likely_source`, `next_commands`, and `param_candidates`.

## Validation check types

| Type | Layer | Notes |
|---|---|---|
| `bbox_size` | post-build | Outer envelope dimensions |
| `watertight` | post-build | STL is a closed manifold |
| `min_triangles` | post-build | Mesh density floor |
| `artifact_exists` | post-build | STEP / STL / SVG present |
| `metadata_equals` | post-build | Asserts a value emitted from `part.py` |
| `outer_diameter_at_z` | post-build | Cross-section radial size at Z |
| `inner_diameter_at_z` | post-build | Inner cavity diameter at Z |
| `section_bbox_at_z` | post-build | Cross-section state or dimensions at Z; `expected` accepts `"solid"`, `"void"`, or `[width, depth]`; `expected: "void"` requires `region` |
| `section_component_count` | post-build | Count disconnected section contours for repeated slots/cavities |
| `diameter_decreases_along_z` | post-build | Monotonicity for tapers / lead-ins |
| `volume_range` | post-build | Volume sanity bounds |
| `min_clearance` | **design-time + post-build** | Pure-shape edge-to-edge clearance between two declared shapes (no STL required) |
| `hole_accessibility` | post-build | Annular clearance around a hole at the working plane; supports X/Y/Z access axes |
| `min_wall_thickness` | post-build | Minimum point-pair distance inside a defined region; supports range mode (axis + range + samples) for multi-slice evaluation |
| `feature_position` | post-build | Assert a 3D point is `solid` or `void` |
| `feature_coverage` | automatic | Every declared feature must reference at least one check |
| `design_schema` | automatic | Field-level schema errors with structured `SchemaIssue` paths, severity, and hints |

The geometric relation checks (`min_clearance`, `hole_accessibility`,
`min_wall_thickness`, `feature_position`) close the historical gap where
`inner_diameter_at_z` would report a correct diameter for a hole that was
half-covered by an adjacent wall.

`agentcad review` treats missing hole-access checks as **blocking** when holes
are declared, and load-bearing attachment features without root/interface checks
as blocking warnings. `agentcad suggest-checks` generates check templates for
the same gaps before validation runs and reports `suggestion_quality` metrics:
template count, placeholder count/ratio, concrete template count, and exact
placeholder paths. A concrete suggestion should use `params.json`,
`metadata.json`, existing checks, geometry bbox, and the probe plan instead of
leaving unresolved `<...>` fields.

## Assembly validation

Assemblies live in `assemblies/<name>/assembly.json` and reference existing
models by component id, model name, and rigid transform. `agentcad assembly
validate <name>` rebuilds stale components, resolves metadata anchors and
interfaces, validates interface schema (cylindrical_male/female, screw_axis,
dovetail, snap_pin/socket, gear_axis, planar), measures declared cylindrical
interfaces against STL sections, emits mate residuals, checks pair coverage,
writes combined/exploded SVG previews, exports `<name>.mjcf.xml`, generates an
interactive `preview.html`, and round-trips the MJCF body/site data against
`assembly_geometry.json`.

Interference validation uses two layers: AABB broad phase first, then a
mesh narrow phase for overlapping component pairs. The narrow phase records
triangle-contact evidence, inside-sample penetration depth, and sampled minimum
surface distance.

## Batch validation and regression

`agentcad validate all` discovers models, variants, and assemblies across the
workspace, runs validation in deterministic order, and emits a project-level
JSON report with per-target summaries and timings.

`agentcad snapshot write` stores normalized snapshots (stripping volatile
timestamps/paths, keeping check results, geometry metrics, and artifact
presence). `agentcad snapshot compare` reports check status drift, geometry
metric drift (bbox, volume, triangles), and artifact changes between current
and baseline — useful for CI regression detection.

## Quick start

```bash
uv tool install agentcad-cli
agentcad --help
```

Create a workspace and start modeling:

```bash
agentcad init my-agentcad-project --model demo
cd my-agentcad-project
claude
```

Then ask Claude to design your target model (for example: "Design an adapter
from an 8025 fan to a round duct") — it will read `CLAUDE.md` in this
workspace and follow the workflow automatically.

For local development:

```bash
uv sync
uv run agentcad --help
```

## Quick example

```bash
agentcad init my-cad-project --model bracket
cd my-cad-project

# 1. Suggest missing checks based on the design contract
agentcad suggest-checks bracket

# 2. Design-time: solve the contract before geometry
agentcad precheck bracket

# 3. Implement part.py, then run the post-build pipeline
agentcad validate bracket

# 4. If interrupted, diagnose workflow gaps
agentcad doctor bracket

# 5. Pre-delivery review, then quality review
agentcad review bracket

# 6. Deliver
agentcad deliver bracket
```

The default generated model is a simple build123d cuboid. Agent rules and
common-error catalog live in `AGENTS.md`, `CLAUDE.md`, and `references/`
(always-on reference docs for build123d patterns and validation strategy).

## Feature helpers

AgentCAD ships a library of geometry helpers that build common mechanical
features and optionally emit contract checks via `ContractBuilder`:

| Helper | What it makes | Tier |
|---|---|---|
| `plate`, `boss`, `rib`, `slot` | Base plate, raised boss, reinforcing rib, routing slot | 1 |
| `duct_socket`, `mounting_pattern`, `stepped_bore`, `knurl`, `sinusoidal_thread` | Cylindrical socket, screw hole pattern, counterbore/countersink, knurled grip, helical thread | 1 |
| `tube`, `prismoid`, `wedge`, `teardrop`, `chamfer_mask`, `nut_trap`, `screw_hole` | Hollow tube, tapered prism, wedge cut, teardrop hole, chamfer edge mask, hex nut pocket, screw clearance hole | 2 |
| `living_hinge_mask`, `threaded_rod`, `dovetail`, `hex_panel`, `snap_pin` + `snap_pin_socket`, `spur_gear` | Flexible hinge cutout, threaded shaft, interlocking dovetail, honeycomb panel, snap-fit pin pair, involute gear | 2 |
| `rounding_mask`, `torus`, `rect_tube`, `pie_slice`, `nut_body`, `nema_mount` | Fillet edge mask, torus ring, rectangular tube, cylindrical sector, hex nut solid, NEMA motor mount | 3 |
| `screw`, `threaded_nut`, `sparse_wall`, `ring_gear` | Screw/bolt solid, threaded nut solid, grid infill wall, internal ring gear | 3 |

Helpers auto-emit contract checks (inner_diameter, section_bbox, volume_range,
etc.) and metadata interfaces (cylindrical_male/female, screw_axis, snap_pin,
dovetail) so every feature gets validation coverage without manual authoring.
A hardware dimension database (`agentcad.hardware`) provides ISO/DIN specs for
screws, nuts, washers, and heat-set inserts.

## Examples

| Path | What it shows |
|---|---|
| `examples/fan-adapter-8025/` | Two validated models plus `assemblies/fan_with_screen/` for inter-model clearance, section, STL, MJCF, and preview validation |
| `examples/iphone15pro-case/` | Real-world phone case with multi-cutouts + section validation |
| `examples/e2e-test/` | Sub-agent end-to-end test: design → precheck → build → validate → review on a mounting bracket |
| `examples/e2e-real-cable-hook/` | Real e2e surface-mounted cable hook with concept + quality review artifacts |
| `examples/e2e-bit-holder/` | Two-part body/lid design that motivated first-class assembly validation |
| `examples/e2e-l-bracket/` | L-shaped bracket demonstrating variants, diff, and fix suggestions |
| `examples/e2e-feature-helpers/` | End-to-end workspace focused on ContractBuilder and Phase 3 helper usage |
| `examples/e2e-feature-demo/` | Smaller helper-driven model used as a feature-library smoke fixture |
| `examples/drone-panel/` | Lightweight drone panel with sparse_wall, hex_panel, torus seal, cover lip |
| `examples/gear-housing/` | Spur + ring gear housing demonstrating gear helpers |
| `examples/pipe-coupling/` | Pipe coupling with tube, dovetail, and chamfer_mask helpers |
| `examples/cadbench/` | Contract-only failure-mode benchmark for evidence/suggest/probe quality gates |

Re-run any example:

```bash
cd examples/fan-adapter-8025
agentcad validate fan_duct_adapter_8025
agentcad review fan_duct_adapter_8025
```

Batch validate the whole workspace:

```bash
cd examples/fan-adapter-8025
agentcad validate all
agentcad snapshot write
agentcad snapshot compare
```

## Tests

```bash
uv run pytest -v
```

The full test suite currently reports 741 passed. It covers CLI dispatch, workspace
scaffolding and sync modes, STL reading and measurement, section extraction and
SVG rendering, JSON IO, post-build validation checks, feature classification,
weak-check severity and review blocking gates, design schema hardening,
negative regression fixtures, min_wall_thickness range mode, metadata interface
schema, ContractBuilder interface emission, feature helpers, hardware lookup
tables, geometric primitives, interactive previews, variants, assembly
validation, batch validation, regression snapshots, workflow diagnostics
(doctor), suggest-checks, CADBench quality gates, suggested-fix enrichment,
timing instrumentation, section cache, executable helper cookbook, and artifact
cleanup. GitHub Actions runs the fast suite on pushes and PRs; slow tests run
on a scheduled/manual workflow.

## Documentation

- [`docs/DESIGN.md`](docs/DESIGN.md) — architecture, first principles, and
  V0–V6 iteration roadmap (with delivered milestones marked).
- [`docs/STATUS.md`](docs/STATUS.md) — current implementation state, recent
  lessons, delivered validation gates, and remaining roadmap direction.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) and
  [`docs/ROADMAP_EXECUTION_PLAN.md`](docs/ROADMAP_EXECUTION_PLAN.md) —
  prioritized future work plus PR-level execution, test, and acceptance plans.
  P0–P4 are marked **Done**; P5 (optional integrations) is next.
- `AGENTS.md` / `CLAUDE.md` (workspace) — operating rules for the coding
  agent, including the 16-stage TDD workflow and the common design-error
  catalog.
