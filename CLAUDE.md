# CLAUDE.md — AgentCAD

## Project Overview

AgentCAD is a CLI-first CAD workflow runtime for coding agents. It provides a repeatable workspace, build/export tools, geometry measurement, SVG previews, validation checks, and delivery manifests so an agent can autonomously create and refine CAD models with measurable feedback.

Core loop: `design contract -> precheck -> params/source -> build -> measure -> render -> validate -> review -> deliver`

The `precheck` and `review` stages are mandatory checkpoints that catch
design-time interferences (before code) and pre-delivery gaps (before
delivery), respectively.

## Tech Stack

- **Language**: Python 3.12 (pinned via `.python-version`; 3.13 rejected due to missing `vtk` wheel)
- **Package manager**: uv (`uv sync`, `uv run agentcad ...`)
- **CAD backend**: build123d
- **Entry point**: `agentcad` CLI command (maps to `agentcad.cli:main`)
- **Build system**: setuptools (pyproject.toml)

## Development Setup

```bash
uv sync
uv run agentcad --help
# Or without install:
PYTHONPATH=src python3 -m agentcad --help
```

## Project Structure

```
src/agentcad/          # Main package
  cli.py               # CLI argument parsing and dispatch
  runner.py             # build123d runner: executes part.py, exports STEP/STL
  workspace.py          # workspace init/new, project discovery, model directory helpers
  measure.py            # STL geometry measurement -> geometry.json
  render.py             # Dependency-free SVG preview renderer from STL
  preview.py            # Interactive HTML preview for models and assemblies
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

All commands auto-detect the workspace by walking up from cwd. 
```bash
agentcad init <workspace> [--model <model>]                          # Initialize workspace (optionally create first model)
agentcad new <model>                                      # Create model inside an existing workspace
agentcad new <model>:<variant>                            # Create variant (same part.py, different params)
agentcad sync                                           # Update workspace scaffold files from templates
agentcad precheck <model>                        # Static design solve before writing part.py
agentcad build <model>[:<variant>]                       # Build + export STEP/STL
agentcad measure <model>[:<variant>]                     # Measure STL geometry
agentcad render <model>                          # SVG preview from STL
agentcad preview <name>[:<variant>]                      # Start local server + interactive browser preview
agentcad preview <name> --static                         # Self-contained offline HTML preview
agentcad preview <name> --kind assembly          # Disambiguate if a model and assembly share a name
agentcad render <model> --section-z <z>                 # Cross-section SVG at Z (also --section-x, --section-y)
agentcad validate <model>[:<variant>]                    # Full validation pipeline
agentcad diff <model> [--last]                   # Compare validation runs
agentcad review <model>                          # Pre-delivery checklist + relations matrix
agentcad deliver <model>[:<variant>]                     # Delivery manifest
agentcad probe <model> --scan --axis z|x|y       # Profile scan for step changes / void detection
agentcad inspect <model>                         # Three-axis scan + section SVGs + suggested probes
agentcad report <model>                                 # Markdown validation report
agentcad assembly init/list/validate/review      # Optional multi-model assembly workflow
```

Preview is a cross-cutting artifact review command, not an assembly subcommand.
Assemblies are optional and only needed for multi-part fit, mate, clearance, or
motion relationships.

All commands return stable machine-readable JSON output. Failures include `stage`, `error.type`, and `error.message`.

## Workspace Protocol

```
project/
  AGENTS.md              # Agent instructions (auto-generated)
  cadproject.json        # Project config
  references/            # build123d-guide.md, validation-strategy.md, images, notes
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
      preview.html
      preview.iso.svg
      <name>.step
      <name>.stl
  assemblies/<name>/
    assembly.json        # Optional multi-model fit/mate contract
    outputs/
      assembly_geometry.json
      assembly_validation.json
      preview.html
      <name>.mjcf.xml
```

## Key Conventions

- `part.py` must assign the final build123d object to a global variable named `result`
- Optional `metadata` variable in `part.py` gets written to `metadata.json`
- Parameters come from `params.json` (loaded at runtime by the model)
- `design.json` is the design contract: it defines `features` and `checks`
- Every feature must reference at least one check (feature coverage is validated)
- Coordinate convention: +X right, +Y back, +Z up
- Units are millimeters unless explicitly stated otherwise
- Generated artifacts live only under `models/<name>/outputs/` or `assemblies/<name>/outputs/`
- After building and validating a model, always run `agentcad preview <name>` and let the human review the 3D result. Do NOT claim the model is complete until the human confirms it looks correct.

## Validation Check Types

Existing: `bbox_size`, `watertight`, `min_triangles`, `artifact_exists`, `metadata_equals`, `outer_diameter_at_z`, `inner_diameter_at_z`, `diameter_decreases_along_z`, `volume_range`, `section_bbox_at_z`, automatic `feature_coverage`.

**Geometric relations (new):**
- `min_clearance` — declarative shape pair clearance ≥ N mm (no STL needed; runs in `agentcad precheck`)
- `hole_accessibility` — tool/bolt envelope can reach a hole at given Z without obstruction
- `min_wall_thickness` — minimum wall thickness in a region at Z
- `feature_position` — a 3D point is in expected solid/void state

Section checks use STL triangle-plane intersections for validating ducts, tapers, sockets, and chamfers. `min_clearance` is a pure-shape check evaluated at design time before any code is written, catching the most common interference bugs (hole edge under a wall, hole-to-edge break, hole-to-hole pitch too tight).

## Release Process

The publish workflow is triggered by pushing a git tag (`vX.Y.Z`). **Never create a GitHub release manually** — the workflow handles PyPI upload and GitHub Release creation. Manual release creation causes a 422 conflict.

Steps to release:
1. Bump `version` in `pyproject.toml`
2. Commit with message `Release X.Y.Z`
3. Tag: `git tag vX.Y.Z`
4. Push: `git push && git push --tags`
5. Wait for the GitHub Actions workflow to complete — it will publish to PyPI and create the GitHub Release

## Running Tests

```bash
uv run pytest -v                    # All tests
uv run pytest tests/test_stl.py     # STL module only
```

Tests cover: CLI dispatch, workspace init/new, STL reading/measurement/section,
SVG rendering, JSON IO, validation checks and feature coverage.

Integration validation through example models:

```bash
cd examples/fan-adapter-8025 && uv run agentcad validate fan_duct_adapter_8025
```
