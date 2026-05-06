# CLAUDE.md — AgentCAD

## Project Overview

AgentCAD is a CLI-first CAD workflow runtime for coding agents. It provides a repeatable workspace, build/export tools, geometry measurement, SVG previews, validation checks, and delivery manifests so an agent can autonomously create and refine CAD models with measurable feedback.

Core loop: `design contract -> params/source -> build -> measure -> render -> validate -> deliver`

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
  stl.py                # Pure-Python STL reader (binary + ASCII), mesh analysis, section radius
  jsonio.py             # JSON read/write/print helpers
  templates.py          # Scaffold templates for init/new commands
  __main__.py           # python -m agentcad entry point
docs/
  DESIGN.md             # Architecture and iteration roadmap (V0-V5)
  STATUS.md             # Current implementation state and lessons learned
examples/
  fan-adapter-8025/     # Example workspace with two validated models
```

## CLI Commands

All commands auto-detect the workspace by walking up from cwd. Use `--project <dir>` only when operating from outside the workspace.

```bash
cad new <model>                                    # Create model (auto-inits workspace if needed)
cad build <model> --json                           # Build + export STEP/STL
cad measure <model> --json                         # Measure STL geometry
cad render <model> --json                          # SVG preview from STL
cad validate <model> --json                        # Full validation pipeline
cad deliver <model> --json                         # Delivery manifest
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

`bbox_size`, `watertight`, `min_triangles`, `artifact_exists`, `metadata_equals`, `outer_diameter_at_z`, `inner_diameter_at_z`, `diameter_decreases_along_z`, `volume_range`, and automatic `feature_coverage`.

Section checks use STL triangle-plane intersections for validating ducts, tapers, sockets, and chamfers.

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
