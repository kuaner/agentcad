# AgentCAD

AgentCAD is a CLI-first CAD workflow runtime for coding agents.

It gives a coding agent a repeatable workspace, a contract-driven modeling
protocol, deterministic build/export, geometric measurement, multi-view
previews, design-time and post-build validation, and a delivery manifest —
so the agent can iterate on CAD models with measurable feedback instead of
visual intuition.

```text
discovery -> concept -> design contract -> precheck -> params/source -> build
          -> measure -> render -> validate -> review -> quality review -> deliver
```

## What's in the box

| Stage | Command | Purpose |
|---|---|---|
| Init | `agentcad init <workspace> [--model <name>]` | Initialize workspace scaffold (optionally create first model) |
| Scaffold | `agentcad new <model>` | Create model folder inside an existing workspace |
| Scaffold | `agentcad new <model>:<variant>` | Create a variant (same `part.py`, different `params.json`) |
| Sync | `agentcad sync` | Refresh workspace scaffold from latest templates |
| Precheck | `agentcad precheck <model>` | Solve `design.json` statically (schema, feature coverage, `min_clearance`) **before** part.py is written |
| Build | `agentcad build <model>[:<variant>]` | Run `part.py` through build123d, export STEP + STL, hash-cache stale runs |
| Measure | `agentcad measure <model>[:<variant>]` | Mesh stats + structural facts (bbox, watertight, triangles, voids) |
| Render | `agentcad render <model>` | Iso/front/top/side/back SVG previews with dimension annotations + Z/X/Y cross-section SVGs with measurement sidecars |
| Preview | `agentcad preview <name>[:<variant>]` | Generate a local `preview.html` for either a model or an assembly, with interactive Three.js STL inspection, component isolation, and geometry/check panels |
| Probe | `agentcad probe <model>` | Cross-section diameter / bbox / component analysis plus ad-hoc line, point, and region measurements; `--scan` to discover step changes |
| Inspect | `agentcad inspect <model>` | Three-axis scan + automatic section SVGs + measurement JSON + suggested probes |
| Validate | `agentcad validate <model>[:<variant>]` | Build + measure + render all orthographic previews + design checks + feature coverage + fix suggestions |
| Diff | `agentcad diff <model> [--last]` | Compare current vs previous validation run: fixed/regressed/stable checks + geometry drift |
| Review | `agentcad review <model>` | Pre-delivery checklist with pairwise relations matrix, hole-access enforcement, and must-view SVG list |
| Assembly | `agentcad assembly init/list/validate/review` | Optional multi-model assembly contracts with component transforms, mate residuals, fit checks, combined/exploded SVGs, preview generation during validation, and mandatory MJCF export |
| Deliver | `agentcad deliver <model>[:<variant>]` | Delivery manifest |
| Report | `agentcad report <model>` | Markdown summary of validation result |

Every command prints stable machine-readable JSON output. Failures include
`stage`, `error.type`, and `error.message`.

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
| `section_bbox_at_z` | post-build | Cross-section AABB / void detection at Z |
| `section_component_count` | post-build | Count disconnected section contours for repeated slots/cavities |
| `diameter_decreases_along_z` | post-build | Monotonicity for tapers / lead-ins |
| `volume_range` | post-build | Volume sanity bounds |
| `min_clearance` | **design-time + post-build** | Pure-shape edge-to-edge clearance between two declared shapes (no STL required) |
| `hole_accessibility` | post-build | Annular clearance around a hole at the working plane; supports X/Y/Z access axes |
| `min_wall_thickness` | post-build | Minimum point-pair distance inside a defined region |
| `feature_position` | post-build | Assert a 3D point is `solid` or `void` |
| `feature_coverage` | automatic | Every declared feature must reference at least one check |

The four "geometric relation" checks (last block) close the historical gap
where `inner_diameter_at_z` would happily report a 4.5 mm hole that was
half-covered by an adjacent wall.

`agentcad review` now treats missing hole-access checks as blocking when holes
are declared, and always requires iso/front/top/side/back previews. The side
view requirement came from a real e2e failure where a retaining lip existed in
the contract but was effectively floating in side projection.

## Assembly validation

Assemblies live in `assemblies/<name>/assembly.json` and reference existing
models by component id, model name, and rigid transform. `agentcad assembly
validate <name>` rebuilds stale components, resolves metadata anchors and
interfaces, measures declared cylindrical interfaces against STL sections,
emits mate residuals, checks pair coverage, writes combined/exploded SVG
previews, exports `<name>.mjcf.xml`, generates an interactive `preview.html`
that can explode the assembly and isolate components one by one, and
round-trips the MJCF body/site data against `assembly_geometry.json`.

Manual preview regeneration uses the same top-level command as single models:
`agentcad preview <name>`. The command auto-detects whether `<name>` is under
`models/` or `assemblies/`; use `--kind model` or `--kind assembly` only when
a model and an assembly intentionally share the same name.

Interference validation now uses two layers: AABB broad phase first, then a
mesh narrow phase for overlapping component pairs. The narrow phase records
triangle-contact evidence, inside-sample penetration depth, and sampled minimum
surface distance, so `interference_free` can distinguish acceptable contact
from real solid penetration.

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

Then ask Claude to design your target model (for example: "Design an adapter from an 8025 fan to a round duct") — it will read `CLAUDE.md` in this workspace and follow the workflow automatically.

For local development:

```bash
uv sync
uv run agentcad --help
```

## Quick example

```bash
agentcad init my-cad-project --model bracket
cd my-cad-project

# 1. Design-time: choose the concept, then solve the contract before geometry
agentcad precheck bracket

# 2. Implement part.py, then run the post-build pipeline
agentcad validate bracket

# 3. Pre-delivery review (relations matrix + must-view SVGs), then quality review
agentcad review bracket

# 4. Deliver
agentcad deliver bracket
```

The default generated model is a simple build123d cuboid. Agent rules and
common-error catalog live in `AGENTS.md`, `CLAUDE.md`, and `references/`
(always-on reference docs for build123d patterns and validation strategy).

## Examples

| Path | What it shows |
|---|---|
| `examples/fan-adapter-8025/` | Two validated models plus `assemblies/fan_with_screen/` for inter-model clearance, section, STL, MJCF, and preview validation |
| `examples/iphone15pro-case/` | Real-world phone case with multi-cutouts + section validation |
| `examples/e2e-test/` | Sub-agent end-to-end test: design → precheck → build → validate → review on a mounting bracket |
| `examples/e2e-real-cable-hook/` | Real e2e surface-mounted cable hook with concept + quality review artifacts |
| `examples/e2e-bit-holder/` | Two-part body/lid design that motivated first-class assembly validation |
| `examples/e2e-l-bracket/` | L-shaped bracket demonstrating variants, diff, and fix suggestions |

Re-run any example:

```bash
cd examples/fan-adapter-8025
agentcad validate fan_duct_adapter_8025
agentcad review fan_duct_adapter_8025
```

## Tests

```bash
uv run pytest -v
```

The test suite covers CLI dispatch, workspace scaffolding, STL
reading and measurement, section extraction and SVG rendering, JSON IO,
post-build validation checks, weak-check warnings, stale build detection,
geometric primitives, interactive previews, assembly validation, and
`precheck` / `review` integration.

## Documentation

- [`docs/DESIGN.md`](docs/DESIGN.md) — architecture, first principles, and
  V0–V5 iteration roadmap (with delivered milestones marked).
- [`docs/STATUS.md`](docs/STATUS.md) — current implementation state, recent
  lessons, delivered validation gates, and remaining roadmap direction.
- `AGENTS.md` / `CLAUDE.md` (workspace) — operating rules for the coding
  agent, including the mandatory TDD red/green workflow and the common
  design-error catalog.
