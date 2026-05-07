# CLAUDE.md — AgentCAD

## Project Overview

AgentCAD is a CLI-first CAD workflow runtime for coding agents. It provides a repeatable workspace, build/export tools, geometry measurement, SVG previews, validation checks, and delivery manifests so an agent can autonomously create and refine CAD models with measurable feedback.

Core loop: `design contract -> precheck -> params/source -> build -> measure -> render -> validate -> review -> deliver`

The `precheck` and `review` stages are mandatory checkpoints that catch
design-time interferences (before code) and pre-delivery gaps (before
delivery), respectively.

## Tech Stack

- **Language**: Python 3.12 (pinned via `.python-version`; 3.13 rejected due to missing `vtk` wheel)
- **Package manager**: uv (`uv sync`, `uv run cad ...`)
- **CAD backend**: build123d
- **Entry points**: `cad` and `agentcad` CLI commands (both map to `agentcad.cli:main`)
- **Build system**: setuptools (pyproject.toml)

## Development Setup

```bash
uv sync
uv run cad --help
# Or without install:
PYTHONPATH=src python3 -m agentcad --help
```

## Project Structure

```
src/agentcad/          # Main package
  cli.py               # CLI argument parsing and dispatch
  runner.py             # build123d runner: executes part.py, exports STEP/STL
  workspace.py          # cad init/new, project discovery, model directory helpers
  measure.py            # STL geometry measurement -> geometry.json
  render.py             # Dependency-free SVG preview renderer from STL
  validate.py           # Full validation pipeline: build + measure + render + design checks + feature coverage
  precheck.py           # Static design-time solver (no STL): clearance + schema + coverage
  review.py             # Pre-delivery checklist + pairwise relations matrix + must-view SVGs
  geometry.py           # Pure shape primitives: AABB, projection, clearance, accessibility
  stl.py                # Pure-Python STL reader (binary + ASCII), mesh analysis, section radius
  section.py            # Cross-section extraction + scan_profile + SVG rendering
  inspect.py            # Three-axis scan + suggested probes (unified inspection)
  probe.py              # Geometric probe: cross-sections + axis scans
  report.py             # Markdown validation report
  jsonio.py             # JSON read/write/print helpers
  templates.py          # Loads template files from _templates/ package
  _templates/           # Template files (md, json, py) for workspace/model scaffolding
  __main__.py           # python -m agentcad entry point
docs/
  DESIGN.md             # Architecture and iteration roadmap (V0-V5)
  STATUS.md             # Current implementation state and lessons learned
examples/
  fan-adapter-8025/     # Example workspace with two validated models
  e2e-test/             # Sub-agent end-to-end test (mounting bracket)
  iphone15pro-case/     # Real-world iPhone 15 Pro phone case
```

## CLI Commands

All commands auto-detect the workspace by walking up from cwd. Use `--project <dir>` only when operating from outside the workspace.

```bash
cad new <model>                                    # Create model (auto-inits workspace if needed)
cad sync                                           # Update workspace scaffold files from templates
cad precheck <model> --json                        # Static design solve before writing part.py
cad build <model> --json                           # Build + export STEP/STL
cad measure <model> --json                         # Measure STL geometry
cad render <model> --json                          # SVG preview from STL
cad render <model> --section-z <z>                 # Cross-section SVG at Z (also --section-x, --section-y)
cad validate <model> --json                        # Full validation pipeline
cad review <model> --json                          # Pre-delivery checklist + relations matrix
cad deliver <model> --json                         # Delivery manifest
cad probe <model> --scan --axis z|x|y --json       # Profile scan for step changes / void detection
cad inspect <model> --json                         # Three-axis scan + section SVGs + suggested probes
cad report <model>                                 # Markdown validation report
```

All commands support `--json` for stable machine-readable output. Failures also return JSON with `stage`, `error.type`, `error.message`.

## Workspace Protocol

```
project/
  AGENTS.md              # Agent instructions (auto-generated)
  cadproject.json        # Project config
  skills/                # build123d-guide.md, validation-strategy.md
  references/            # Images, sketches, notes
  models/<name>/
    README.md
    design.json          # Feature contract + validation checks
    params.json          # Tunable dimensions
    part.py              # build123d geometry (must assign to `result`)
    metadata.json        # Optional: emitted by part.py via `metadata` variable
    outputs/
      build.json
      geometry.json
      validation.json
      deliverable.json
      preview.iso.svg
      <name>.step
      <name>.stl
```

## Key Conventions

- `part.py` must assign the final build123d object to a global variable named `result`
- Optional `metadata` variable in `part.py` gets written to `metadata.json`
- Parameters come from `params.json` (loaded at runtime by the model)
- `design.json` is the design contract: it defines `features` and `checks`
- Every feature must reference at least one check (feature coverage is validated)
- Coordinate convention: +X right, +Y back, +Z up
- Units are millimeters unless explicitly stated otherwise
- Generated artifacts live only under `models/<name>/outputs/`

## Validation Check Types

Existing: `bbox_size`, `watertight`, `min_triangles`, `artifact_exists`, `metadata_equals`, `outer_diameter_at_z`, `inner_diameter_at_z`, `diameter_decreases_along_z`, `volume_range`, `section_bbox_at_z`, automatic `feature_coverage`.

**Geometric relations (new):**
- `min_clearance` — declarative shape pair clearance ≥ N mm (no STL needed; runs in `cad precheck`)
- `hole_accessibility` — tool/bolt envelope can reach a hole at given Z without obstruction
- `min_wall_thickness` — minimum wall thickness in a region at Z
- `feature_position` — a 3D point is in expected solid/void state

Section checks use STL triangle-plane intersections for validating ducts, tapers, sockets, and chamfers. `min_clearance` is a pure-shape check evaluated at design time before any code is written, catching the most common interference bugs (hole edge under a wall, hole-to-edge break, hole-to-hole pitch too tight).

## Running Tests

```bash
uv run pytest -v                    # All tests
uv run pytest tests/test_stl.py     # STL module only
```

Tests cover: CLI dispatch, workspace init/new, STL reading/measurement/section,
SVG rendering, JSON IO, validation checks and feature coverage.

Integration validation through example models:

```bash
cd examples/fan-adapter-8025 && uv run cad validate fan_duct_adapter_8025 --json
```
