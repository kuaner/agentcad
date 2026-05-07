# AgentCAD

AgentCAD is a CLI-first CAD workflow runtime for coding agents.

It gives a coding agent a repeatable workspace, a contract-driven modeling
protocol, deterministic build/export, geometric measurement, multi-view
previews, design-time and post-build validation, and a delivery manifest —
so the agent can iterate on CAD models with measurable feedback instead of
visual intuition.

```text
design contract -> precheck -> params/source -> build
                  -> measure -> render -> validate -> review -> deliver
```

## What's in the box

| Stage | Command | Purpose |
|---|---|---|
| Init | `agentcad init <workspace> [--model <name>]` | Initialize workspace scaffold (optionally create first model) |
| Scaffold | `agentcad new <model>` | Create model folder inside an existing workspace |
| Sync | `agentcad sync` | Refresh workspace scaffold from latest templates |
| Precheck | `agentcad precheck <model>` | Solve `design.json` statically (schema, feature coverage, `min_clearance`) **before** part.py is written |
| Build | `agentcad build <model>` | Run `part.py` through build123d, export STEP + STL, hash-cache stale runs |
| Measure | `agentcad measure <model>` | Mesh stats + structural facts (bbox, watertight, triangles, voids) |
| Render | `agentcad render <model>` | Iso/front/top/side/back SVG previews + Z/X/Y cross-section SVGs |
| Probe | `agentcad probe <model>` | Cross-section diameter / bbox / void at specified Z, X, Y; `--scan` to discover step changes |
| Inspect | `agentcad inspect <model>` | Three-axis scan + automatic section SVGs + suggested probes |
| Validate | `agentcad validate <model>` | Build + measure + render + design checks + feature coverage; auto-emits debug SVGs on failure |
| Review | `agentcad review <model>` | Pre-delivery checklist with pairwise relations matrix and must-view SVG list |
| Deliver | `agentcad deliver <model>` | Delivery manifest |
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
| `diameter_decreases_along_z` | post-build | Monotonicity for tapers / lead-ins |
| `volume_range` | post-build | Volume sanity bounds |
| `min_clearance` | **design-time + post-build** | Pure-shape edge-to-edge clearance between two declared shapes (no STL required) |
| `hole_accessibility` | post-build | Annular clearance around a hole at the working plane |
| `min_wall_thickness` | post-build | Minimum point-pair distance inside a defined region |
| `feature_position` | post-build | Assert a 3D point is `solid` or `void` |
| `feature_coverage` | automatic | Every declared feature must reference at least one check |

The four "geometric relation" checks (last block) close the historical gap
where `inner_diameter_at_z` would happily report a 4.5 mm hole that was
half-covered by an adjacent wall.

## Quick start

```bash
uv tool install agentcad-cli
agentcad --help
```

Create a workspace and start modeling:

```bash
agentcad init my-agentcad-project --model demo
cd my-agentcad-project
```

Then open this directory in Claude Code / Cursor and continue from
`models/demo/part.py`.

For local development:

```bash
uv sync
uv run agentcad --help
```

## Quick example

```bash
agentcad init my-cad-project --model bracket
cd my-cad-project

# 1. Design-time: solve the contract before writing geometry
agentcad precheck bracket

# 2. Implement part.py, then run the post-build pipeline
agentcad validate bracket

# 3. Pre-delivery review (relations matrix + must-view SVGs)
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
| `examples/fan-adapter-8025/` | Two validated models: a fan-to-duct adapter and a magnetic outlet plate |
| `examples/iphone15pro-case/` | Real-world phone case with multi-cutouts + section validation |
| `examples/e2e-test/` | Sub-agent end-to-end test: design → precheck → build → validate → review on a mounting bracket |

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

125 tests at last count, covering CLI dispatch, workspace scaffolding, STL
reading and measurement, section extraction and SVG rendering, JSON IO,
post-build validation checks, weak-check warnings, stale build detection,
geometric primitives, and `precheck` / `review` integration.

## Documentation

- [`docs/DESIGN.md`](docs/DESIGN.md) — architecture, first principles, and
  V0–V5 iteration roadmap (with delivered milestones marked).
- [`docs/STATUS.md`](docs/STATUS.md) — current implementation state, recent
  lessons (build123d traps, hole-wall interference), and the planned next
  research and engineering work.
- `AGENTS.md` / `CLAUDE.md` (workspace) — operating rules for the coding
  agent, including the mandatory TDD red/green workflow and the common
  design-error catalog.
