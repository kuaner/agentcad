# CLAUDE.md — AgentCAD

## Project Overview

AgentCAD is a CLI-first CAD workflow runtime for coding agents. It provides a repeatable workspace, build/export tools, geometry measurement, SVG and interactive HTML previews, validation checks, feature helpers, assembly checks, and delivery manifests so an agent can autonomously create and refine CAD models with measurable feedback.

Core loop: `discovery -> concept -> design contract -> suggest-checks -> precheck -> params/source -> build -> measure -> render -> preview -> validate -> review -> quality review -> deliver`

The `precheck` and `review` stages are mandatory checkpoints that catch
design-time interferences (before code) and pre-delivery gaps (before
delivery), respectively.

## Tech Stack

- **Language**: Python 3.12 for local/CI use (pinned via `.python-version`; package supports `>=3.11,<3.13`; 3.13 rejected due to missing `vtk` wheel)
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
  batch.py              # Batch validation: target discovery + workspace-level orchestration
  snapshot.py           # Regression snapshots: write, load, compare normalized validation data
  doctor.py             # Workflow state diagnostics: severity-graded findings + recommended next commands
  suggest/              # Suggest missing checks, concrete templates, and suggestion quality metrics
  cadbench.py           # Contract-fixture benchmark for evidence/suggest/probe quality gates
  metadata.py           # Metadata interface schema validation and resolution
  clean.py              # Artifact cleanup: validation history, debug SVGs, retention policy
  _templates/           # Template files (md, json, py) for workspace/model scaffolding
  features/             # Helper library: reusable CAD primitives + ContractBuilder integration
  hardware/             # Screw, nut, washer, heat-set insert dimension tables
  __main__.py           # python -m agentcad entry point
docs/
  DESIGN.md             # Architecture and iteration roadmap (V0-V6)
  STATUS.md             # Current implementation state and lessons learned
examples/
  fan-adapter-8025/     # Two validated models plus fan_with_screen assembly
  e2e-bit-holder/       # Body/lid assembly fixture
  e2e-feature-helpers/  # ContractBuilder/helper e2e fixture
  drone-panel/          # Helper-driven lightweight panel
  gear-housing/         # Gear helper fixture
  pipe-coupling/        # Tube/dovetail/chamfer helper fixture
  iphone15pro-case/     # Real-world iPhone 15 Pro phone case
  cadbench/             # Contract-only failure-mode fixtures for suggest/probe quality gates
```

## CLI Commands

All commands auto-detect the workspace by walking up from cwd. 
```bash
agentcad init <workspace> [--model <model>]                          # Initialize workspace (optionally create first model)
agentcad new <model>                                      # Create model inside an existing workspace
agentcad new <model>:<variant>                            # Create variant (same part.py, different params)
agentcad sync [--dry-run] [--only <path>] [--prune-deprecated]  # Update workspace scaffold files from templates
agentcad precheck <model>                        # Static design solve before writing part.py
agentcad build <model>[:<variant>]                       # Build + export STEP/STL
agentcad measure <model>[:<variant>]                     # Measure STL geometry
agentcad render <model>                          # SVG preview from STL
agentcad render <model> --views iso,front,top    # Render multiple SVG previews
agentcad preview <name>[:<variant>]                      # Start local server + interactive browser preview (auto-opens browser)
agentcad preview <name> --static                         # Self-contained offline HTML preview (auto-opens browser, no server needed)
agentcad preview <name> --kind assembly          # Disambiguate if a model and assembly share a name
agentcad render <model> --section-z <z>                 # Cross-section SVG at Z (also --section-x, --section-y)
agentcad validate <model>[:<variant>]                    # Full validation pipeline
agentcad validate all [--models] [--assemblies] [--include-variants] \
  [--include-slow] [--fail-fast] [--output <path>]      # Batch validate all workspace targets
agentcad validate all --changed-only                     # Currently returns explicit NotImplemented JSON
agentcad snapshot write [--target <name>|<model>:<variant>]    # Write regression snapshots
agentcad snapshot compare [--target <name>|<model>:<variant>]  # Compare current vs baseline snapshots
agentcad diff <model> [--last]                   # Compare validation runs
agentcad review <model>[:<variant>]              # Pre-delivery checklist + relations matrix
agentcad deliver <model>[:<variant>]                     # Delivery manifest
agentcad probe <model> --z <z> --cx <x> --cy <y> # Radial center aliases
agentcad probe <model> --scan --axis z|x|y       # Profile scan for step changes / void detection
agentcad inspect <model>                         # Three-axis scan + section SVGs + suggested probes
agentcad report <model>                                 # Markdown validation report
agentcad suggest-checks <model>                 # Suggest missing checks based on design contract
agentcad cadbench [--root examples/cadbench]     # Evaluate CADBench contract fixtures
agentcad doctor <model>[:<variant>]               # Workflow state diagnostics: gaps, severity, next command
agentcad clean [--model <name>] [--dry-run] [--debug] [--previews]  # Remove debug/history artifacts
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

## Documentation Maintenance

This project has **two CLAUDE.md files** serving different audiences. When you
make changes to the project (new commands, new modules, changed conventions),
you must update **both** — not just one.

1. **Root `CLAUDE.md`** (this file) — audience: agents **developing** the
   agentcad project. Covers tech stack, project structure, CLI reference,
   conventions, pitfalls, release process, running tests. Update this file when:
   - Adding new modules (update Project Structure)
   - Adding new CLI commands (update CLI Commands)
   - Changing test count (update Running Tests)
   - Adding new pitfalls or conventions

2. **Template `CLAUDE.md`**
   (`src/agentcad/_templates/workspace/CLAUDE.md`) — audience: agents **using**
   agentcad to create CAD models. Covers 16-stage workflow, iteration loop, hard
   rules, workspace layout, CLI quick reference. Update this file when:
   - Adding new CLI commands (update CLI Quick Reference)
   - Changing workflow stages or hard rules
   - Changing workspace layout or conventions that affect modeling behavior

The template file is copied into every new workspace via `agentcad init` and
propagated to existing workspaces via `agentcad sync`. The root file stays in
the project repo only. If you add a command but forget the template, users will
never discover it — so always check both files after a change.

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

## build123d Pitfalls

- **Never use `fuse()` + `add(mode=Mode.SUBTRACT)` for through-holes.** The boolean subtraction on fused Parts produces incomplete cuts — holes that stop partway through the solid even when the cylinder geometry extends past both faces. Use `Locations` + `Cylinder(mode=Mode.SUBTRACT)` directly inside the `BuildPart` context instead. The feature helpers `MountingHoles.cut()` and `SteppedBore.cut()` already use this pattern.
- **Always add overshoot to subtraction cylinders.** A cylinder exactly matching the material thickness leaves paper-thin faces at the boundaries. Add 1mm overshoot and offset the start by 0.5mm so the cylinder extends past both faces.
- **`inner_diameter_at_z` at mid-Z can pass even when holes are shallow.** A through-hole check at Z=depth/2 only proves the hole exists at that Z level. Verify with sections at Z near 0 (bottom) and Z near top to confirm full penetration.

## Validation Check Types

Existing: `bbox_size`, `watertight`, `min_triangles`, `artifact_exists`, `metadata_equals`, `outer_diameter_at_z`, `inner_diameter_at_z`, `diameter_decreases_along_z`, `volume_range`, `section_bbox_at_z`, `section_component_count`, automatic `feature_coverage`.

**Geometric relations (new):**
- `min_clearance` — declarative shape pair clearance ≥ N mm (no STL needed; runs in `agentcad precheck`)
- `hole_accessibility` — tool/bolt envelope can reach a hole at given Z without obstruction
- `min_wall_thickness` — minimum wall thickness in a region at Z; supports range mode (axis + range + samples) for multi-slice evaluation
- `feature_position` — a 3D point is in expected solid/void state

Section checks use STL triangle-plane intersections for validating ducts, tapers, sockets, and chamfers. `min_clearance` is a pure-shape check evaluated at design time before any code is written, catching the most common interference bugs (hole edge under a wall, hole-to-edge break, hole-to-hole pitch too tight).

Schema validation now uses structured `SchemaIssue` with field-level error paths, severity (error/warning), and hints. `section_bbox_at_z` with `expected: "void"` emits a warning if `region` is missing (false-pass risk on empty slices). `min_wall_thickness` validates single-plane vs range-mode schema before evaluation.

Weak-check warnings are now categorized with severity levels:
- Features without any checks or without geometry checks → `severity: "blocking"` (gates delivery in review)
- Hole-like features without `hole_accessibility` → `severity: "blocking"`
- Load-bearing attachment features (rib/boss/tab) without root/interface checks → `severity: "warning"` (deferred followup)

Feature classification (`classify_feature`) uses keyword matching on feature id, intent, and description to tag features as `hole`, `load_bearing_attachment`, or `interface`. Review promotes blocking-severity warnings to checklist items that gate `ready_to_deliver`.

`agentcad suggest-checks` now includes a `suggestion_quality` payload with
`template_count`, `placeholder_count`, `placeholder_ratio`, concrete template
count, and exact placeholder paths. New suggest templates should use
`params.json`, `metadata.json`, measured geometry, existing checks, and probe
plans to avoid unresolved `<...>` values. `examples/cadbench` is the hard gate
for these behaviors: evidence coverage, suggested check coverage, probe command
relevance, and placeholder budgets must pass.

Metadata interface schema (`metadata.py`) validates the `interfaces` and `anchors` sections of `metadata.json` with structured `SchemaIssue` error paths. Supported interface kinds: `cylindrical_male`, `cylindrical_female`, `screw_axis`, `dovetail_rail`, `snap_pin`, `snap_socket`, `gear_axis`, `planar`. Assembly validation converts metadata schema errors into `metadata_schema` checks. `ContractBuilder.add_interface()` accumulates interface entries and `write_metadata_to()` writes/merges them into `metadata.json`.

Feature helpers that auto-emit interfaces when a builder is provided: `tube` (outer_sleeve + inner_bore), `duct_socket` (socket), `SteppedBore/ScrewHole` (screw_axis), `snap_pin` (pin), `snap_pin_socket` (socket).

## Feature Helpers

Use `agentcad.features` for repeated mechanical primitives when it fits the model. Helpers return build123d geometry and can register feature/check records through `ContractBuilder`. The public helper set includes plates, bosses, ribs, slots, tubes, screw holes, stepped bores, mounting patterns, duct sockets, hinges, dovetails, snap pins, sparse walls, NEMA mounts, threaded rods/nuts, screws, knurls, spur gears, and ring gears. Hardware dimensions live under `agentcad.hardware`.

## Release Process

The publish workflow is triggered by pushing a git tag (`vX.Y.Z`). **Never create a GitHub release manually** — the workflow handles PyPI upload and GitHub Release creation. Manual release creation causes a 422 conflict.

Steps to release:
1. Bump `version` in `pyproject.toml` only. Do not manually edit
   `src/agentcad/__init__.py`; `agentcad.__version__` is derived from
   `pyproject.toml` in a source checkout and package metadata when installed.
2. Commit with message `Release X.Y.Z`
3. Tag: `git tag vX.Y.Z`
4. Push: `git push && git push --tags`
5. Wait for the GitHub Actions workflow to complete — it will publish to PyPI and create the GitHub Release

## Running Tests

```bash
uv run pytest -v                    # All tests
uv run pytest tests/test_stl.py     # STL module only
```

The full suite currently reports 741 passed with
`uv run pytest -q`. Coverage includes CLI dispatch, workspace
init/new/sync, STL reading/measurement/section, SVG rendering, interactive
previews, JSON IO, validation checks, feature coverage, feature helpers,
hardware lookup tables, variants, diff, assemblies, precheck, review, batch
validation, regression snapshots, contract schema hardening, min_wall_thickness
range mode, negative regression fixtures, review blocking gates, metadata
interface schema, ContractBuilder interface emission, doctor diagnostics,
suggest-checks, CADBench quality gates, improved suggested_fix payloads, timing
instrumentation, section cache, executable helper cookbook, and artifact
cleanup.

Integration validation through example models:

```bash
cd examples/fan-adapter-8025 && uv run agentcad validate fan_duct_adapter_8025
```
