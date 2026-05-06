# AgentCAD Current Status

Last updated: 2026-05-06

## Project Goal

AgentCAD is a CLI-first workflow runtime for coding agents that create CAD
models. The core loop is:

```text
feature contract -> params/source -> build -> measure -> render -> validate -> deliver
```

The project is intentionally agent-first. It does not currently include a
desktop UI, web viewer, or MCP server.

## Environment

Use `uv`.

```bash
cd /Users/kuaner/Documents/code/agentcad
uv sync
uv run cad --help
```

Important dependency note:

- `build123d` is a required dependency.
- `.python-version` pins Python `3.12`.
- Python 3.13 was tested and rejected because the required `vtk==9.3.1` wheel
  is not available for `cp313`.

## Implemented CLI

Entry point:

```bash
uv run cad ...
```

Commands:

```bash
cad init <project>
cad new --project <project> <model>
cad build --project <project> <model> --json
cad measure --project <project> <model> --json
cad render --project <project> <model> --view iso --json
cad validate --project <project> <model> --json
cad deliver --project <project> <model> --json
```

`cad validate` is the main agent self-check command. It runs build, measure,
render, feature coverage, design checks, and artifact checks.

## Current Workspace Layout

V0 intentionally has no project-root `outputs/` directory. Generated artifacts
belong to each model:

```text
project/
  AGENTS.md
  cadproject.json
  skills/
  references/
  models/
    <model>/
      README.md
      design.json
      params.json
      part.py
      metadata.json
      outputs/
        build.json
        geometry.json
        validation.json
        preview.iso.svg
        <model>.step
        <model>.stl
        deliverable.json
```

## Key Design Change

The project now requires a Feature Contract before geometry implementation.

`design.json` supports:

- `features`: explicit user-visible or functional design intent
- `checks`: measurable validation checks
- feature-to-check coverage: every feature must reference at least one existing
  check or validation fails

This change came from a real failure: a lead-in chamfer was initially written in
code but hidden by an overlapping cylinder. BBox/watertight checks did not catch
it. The fix was to add feature-level and section-level checks.

## Validation Features

Implemented check types:

- `bbox_size`
- `watertight`
- `min_triangles`
- `artifact_exists`
- `metadata_equals`
- `outer_diameter_at_z`
- `inner_diameter_at_z`
- `diameter_decreases_along_z`
- automatic `feature_coverage`

Section checks use STL triangle-plane intersections and are useful for ducts,
tapers, sockets, and chamfers.

## Example Project

Example workspace:

```text
examples/fan-adapter-8025/
```

It contains two validated models.

### 1. Fan To Duct Adapter

Path:

```text
examples/fan-adapter-8025/models/fan_duct_adapter_8025/
```

Purpose:

- Adapter from an 8025 fan to an 80 mm inner-diameter round duct.
- Square flange bolts to fan.
- Round male socket slips into duct.

Key dimensions:

- fan frame: `80 x 80 x 25 mm`
- mount spacing: `71.5 mm`
- flange: `86 x 86 x 5 mm`
- duct target inner diameter: `80 mm`
- socket OD: `79.4 mm`
- socket length: `28 mm`
- bbox: `86 x 86 x 33 mm`

Current validation highlights:

```text
validation passed
watertight: true
triangles: 5836
lead-in diameter:
  z=32.0 -> 79.4000 mm
  z=32.5 -> 78.4000 mm
  z=33.0 -> 77.4000 mm
```

Artifacts:

```text
outputs/fan_duct_adapter_8025.step
outputs/fan_duct_adapter_8025.stl
outputs/preview.iso.svg
outputs/geometry.json
outputs/validation.json
outputs/deliverable.json
```

Re-run:

```bash
uv run cad validate --project examples/fan-adapter-8025 fan_duct_adapter_8025 --json
uv run cad deliver --project examples/fan-adapter-8025 fan_duct_adapter_8025 --json
```

### 2. Outlet Magnetic Screen Plate

Path:

```text
examples/fan-adapter-8025/models/outlet_magnetic_screen_plate_8025/
```

Purpose:

- Outlet-side adapter plate for an 8025 fan.
- Screws to fan using the normal 71.5 mm fan hole pattern.
- Same four corner positions include coaxial stepped holes:
  - screen/service-side magnet pocket for glued `12 mm x 5 mm` magnets
  - screen/service-side screw head recess below the magnet pocket
  - through screw clearance hole into the fan
- Intended to magnetically attach the fan assembly to a window screen for
  exhaust.

Important assembly correction:

The screw and magnet features are on the same accessible side. Screws are
installed first from the screen/service side into the fan, then magnets are
glued into the larger pockets above the screw heads.

Key dimensions:

- plate: `88 x 88 x 9 mm`
- mount spacing: `71.5 mm`
- screw clearance: `4.5 mm`
- screw head recess: `8.5 mm x 2.0 mm`
- magnet pocket: `12.2 mm x 5.2 mm`
- center exhaust opening: `74 mm`

Current validation highlights:

```text
validation passed
bbox: 88 x 88 x 9 mm
watertight: true
triangles: 7096
screw_install_side: screen
screw_head_recess_side: screen
magnet_pocket_side: screen
magnet pockets coaxial with mounting holes: true
```

Artifacts:

```text
outputs/outlet_magnetic_screen_plate_8025.step
outputs/outlet_magnetic_screen_plate_8025.stl
outputs/preview.iso.svg
outputs/geometry.json
outputs/validation.json
outputs/deliverable.json
```

Re-run:

```bash
uv run cad validate --project examples/fan-adapter-8025 outlet_magnetic_screen_plate_8025 --json
uv run cad deliver --project examples/fan-adapter-8025 outlet_magnetic_screen_plate_8025 --json
```

## Important Lessons From The Two Runs

1. BBox and watertight are necessary but insufficient.
2. Every requested feature needs a validation check.
3. Metadata checks are useful for design intent but should not be the only
   evidence for actual geometry.
4. Section checks are useful for catching hidden or ineffective chamfers/tapers.
5. The spec must explicitly define assembly direction, not just dimensions.
6. Model outputs should live under `models/<name>/outputs/` only.

## Next Recommended Work

Short-term:

- Add real geometry checks for hole/pocket diameters at specific XY positions.
- Add section checks for stepped bores, not just centered cylindrical sections.
- Add `cad validate all`.
- Add a human-readable Markdown report command.
- Add a cleaner preview renderer or PNG export.

Medium-term:

- Add JSON schema validation for `design.json`.
- Introduce feature trace output from model code or helper library.
- Add reusable helper functions for common CAD features:
  - fan mounting pattern
  - stepped bore
  - magnet pocket
  - duct socket
  - plate with rounded corners

Open design question:

- Whether to keep models as raw build123d source plus Feature Contract, or
  introduce a small helper library first. Avoid a full CAD DSL until repeated
  patterns justify it.
