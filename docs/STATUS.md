# AgentCAD Current Status

Last updated: 2026-05-10

## Project Goal

AgentCAD is a CLI-first workflow runtime for coding agents that create CAD
models. The expanded core loop is:

```text
discovery -> concept -> design contract -> precheck -> params/source -> build
          -> measure -> render -> validate -> review -> quality review -> deliver
```

`precheck` and `review` are mandatory checkpoints that catch design-time
interferences before any code is written and pre-delivery gaps before any
artifact is shipped, respectively. The prompt templates now also include a
Concept Gate before `design.json` and a Design Quality Review before delivery,
so agents have to reason about topology and design quality, not only geometric
validity. The project remains intentionally agent-first: there is no desktop
UI, web viewer, or MCP server in the core loop.

## Environment

```bash
cd /Users/kuaner/Documents/code/agentcad
uv sync
uv run agentcad --help
```

- `build123d` is a required dependency.
- `.python-version` pins Python `3.12`.
- Python 3.13 was tested and rejected because the required `vtk==9.3.1`
  wheel is not available for `cp313`.

## Implemented CLI

```bash
agentcad init <workspace> [--model <model>]                          # scaffold workspace (and optional first model)
agentcad new <model>                                      # add model in existing workspace
agentcad new <model> --variant <name>                     # create variant (same part.py, different params)
agentcad sync                                            # refresh workspace files from templates
agentcad precheck <model>                         # design-time solve before code
agentcad build <model> [--variant <name>] [--force]       # build123d -> STEP + STL (hash-cached)
agentcad measure <model> [--variant <name>]               # mesh stats + structural facts
agentcad render <model> --view iso                # iso/front/top/side/back SVG
agentcad render <model> --section-z <z>                  # cross-section SVG + JSON sidecar (also --section-x, --section-y)
agentcad probe <model> --z <z>                    # cross-section diameters / void / section analysis
agentcad probe <model> --z <z> --line-u <u>       # active line measurement
agentcad probe <model> --z <z> --point u,v        # nearest contour distance
agentcad probe <model> --scan --axis x|y|z        # axis profile + step changes
agentcad inspect <model>                          # three-axis scan + auto sections + suggested probes
agentcad validate <model> [--variant <name>]              # build + measure + render + design checks + fix suggestions
agentcad diff <model> [--last]                             # compare validation runs
agentcad review <model>                           # pre-delivery checklist + relations matrix
agentcad deliver <model> [--variant <name>]               # delivery manifest
agentcad preview <name> [--kind model|assembly] [--variant <name>]  # interactive HTML preview
agentcad report <model>                                  # Markdown validation summary
```

`agentcad validate` is the post-build self-check. `agentcad precheck` and
`agentcad review` flank it as design-time and pre-delivery gates.

## Workspace Layout

Generated artifacts live exclusively under `models/<name>/outputs/`. There
is intentionally no project-root `outputs/` directory.

```text
project/
  AGENTS.md
  CLAUDE.md
  cadproject.json
  references/
    build123d-guide.md
    validation-strategy.md
    images/
    notes.md
  models/
    <model>/
      README.md
      design.json
      params.json
      part.py
      metadata.json
      variants/
        <variant>/
          params.json
      outputs/
        precheck.json
        build.json
        geometry.json
        validation.json
        validation-history/
          <timestamp>.json
        observability.json
        review.json
        deliverable.json
        preview.html
        preview.{iso,front,top,side,back}.svg
        section.{x,y,z}{value}.svg
        section.{x,y,z}{value}.json
        debug.<check_id>.{x,y,z}{value}.svg
        <model>.step
        <model>.stl
      outputs/<variant>/
        (same structure, variant-specific)
```

## Design Contract

`design.json` fields:

- `features`: explicit user-visible / functional design intent (with `id`)
- `checks`: measurable validation entries (each must have an `id` and one of
  the supported `type`s)
- coverage rule: every feature must reference at least one check, otherwise
  validation fails with a `feature_coverage` error

This contract was driven by repeated real failures: a lead-in chamfer
hidden by an overlapping cylinder; a hole-wall interference that
`inner_diameter_at_z` happily reported as passing. The fix is layered: a
strong contract, design-time relational checks, and a pre-delivery review
checklist.

## Validation check types

Post-build mesh checks:

- `bbox_size`
- `watertight`
- `min_triangles`
- `artifact_exists`
- `metadata_equals`
- `outer_diameter_at_z`
- `inner_diameter_at_z`
- `section_bbox_at_z` (solid / void / explicit dimensions)
- `section_component_count`
- `diameter_decreases_along_z`
- `volume_range`
- automatic `feature_coverage`

Geometric relation checks (added in the latest milestone):

- `min_clearance` — declarative shape pair, edge-to-edge distance ≥ N mm.
  Evaluated **statically** in `agentcad precheck` (no STL needed) and again in
  `agentcad validate` for sanity.
- `hole_accessibility` — annular tool envelope around a hole is free of
  material at the working plane. It now supports X/Y/Z approach axes so
  vertical-wall screws can be checked on an XZ approach plane.
- `min_wall_thickness` — minimum point-pair distance inside a region at Z.
- `feature_position` — assert a 3D point is `solid` or `void` (used to pin
  feature direction or guard blind-hole bottoms).

`min_clearance` is the headline win: the most common interference bug
("hole edge buried under a wall") is caught the moment `design.json` is
finalized — long before any geometry is generated.

## Example workspaces

```text
examples/
  fan-adapter-8025/      # original V0 ducting models
  iphone15pro-case/      # full-cutout phone case with section checks
  e2e-test/              # sub-agent run that produced mounting_bracket
  e2e-real-cable-hook/   # real e2e wall hook with concept + quality review
```

### 1. Fan duct adapter (`fan-adapter-8025/fan_duct_adapter_8025`)

Adapter from an 8025 fan to an 80 mm round duct. Square flange bolts to
the fan, round male socket slips into the duct, lead-in chamfer at the
duct end.

- frame `80 × 80 × 25 mm`
- mount spacing `71.5 mm`
- flange `86 × 86 × 5 mm`
- duct ID `80 mm`, socket OD `79.4 mm`, socket length `28 mm`
- bbox `86 × 86 × 33 mm`

Section checks confirm the lead-in tapers monotonically from `79.4 → 77.4 mm`.

### 2. Outlet magnetic screen plate

Adapter plate that screws to the fan and magnetically attaches to a window
screen. Coaxial stepped holes per corner: through-hole into the fan, head
recess above it, magnet pocket above that. The contract pins
`screw_install_side`, `screw_head_recess_side`, and `magnet_pocket_side`
with metadata equality so the assembly direction is part of validation.

### 3. iPhone 15 Pro case (`iphone15pro-case`)

Real-world TPU/PETG case with multi-cutout pockets (camera, action button,
USB-C, mute). The `section_bbox_at_z` check is exercised heavily here; an
early bug had `Locations + BuildSketch(Plane.XY)` silently dropping the Z
offset, which surfaced because section checks failed even though
`bbox_size` and `watertight` passed.

### 4. Sub-agent end-to-end test (`e2e-test/mounting_bracket`)

A sub-agent without prior context was asked to design an L-shaped mounting
bracket via the documented TDD workflow. The result successfully produced
the model and incidentally surfaced two real bugs:

1. A new build123d trap — `Box(...).moved(Location(...))` inside a
   `BuildPart` context double-adds the shape (once at the original
   position, once at the moved position). The fix is to use
   `with Locations((x, y, z)): Box(...)`. This is now codified in
   `references/build123d-guide.md`.
2. A real **hole-wall interference**: the M4 base holes were partly buried
   under the upright wall, yet `inner_diameter_at_z` was passing because
   it only verified that the hole *exists* at that Z, not that its
   *footprint* is clear. The fix landed in two parts:
   - a parameter change (`base_hole_y_offset 15 → 13 mm`) to restore the
     0.75 mm clearance;
   - new `min_clearance` and `hole_accessibility` checks added to the
     contract so the same class of bug is caught at design time
     henceforth.

### 5. Real cable-hook e2e (`e2e-real-cable-hook/wall_cable_hook`)

This run exposed a different class of failure: a model can satisfy local checks
and still look structurally wrong in side view.

Findings folded back into the project:

- A horizontal/top-plate topology was rejected and replaced with a true
  vertical back plate plus forward hook arm.
- Screw holes moved to left/right upper wings so the screwdriver path is not
  hidden behind the hook body.
- The front retaining lip initially existed but was effectively hanging from a
  thin top-edge overlap in `preview.side.svg`. The contract now includes a
  `front_lip_base_connected` check at the hook-arm height.
- `agentcad validate` now renders all five core views by default.
- `agentcad review` treats iso/front/top/side/back previews as required
  `must_view` artifacts and blocks declared holes that lack access checks.

## Lessons consolidated

1. `bbox_size` + `watertight` are necessary but never sufficient.
2. Every feature needs a geometry-specific check — diameter, section,
   clearance, accessibility, or wall thickness — not just a bbox.
3. **Reason in edges, not centers.** The classic human error is
   `hole_y(15) - wall_y(16) = 1 mm`, forgetting the hole's 2.25 mm radius.
   The mitigation is `min_clearance` working on shape descriptors, where
   edges are computed for you.
4. Metadata checks pin design intent (assembly direction, install side)
   but cannot replace mesh-level checks for actual geometry.
5. Section checks catch hidden / ineffective tapers and chamfers.
6. `agentcad probe --scan` reveals step changes (cavity start, wall transitions)
   that are otherwise invisible in iso previews; `point_count` deltas catch
   hollow shells that have constant outer-bbox profiles.
7. A feature body check is not a connection check. For lips, ribs, tabs, bosses,
   arms, and other load-bearing attachments, require a root/interface check.
8. Treat section measurement JSON as the first-pass truth. SVGs are still
   useful, but bbox, component count, closed-loop ratio, and warnings make
   geometry failures easier for agents to detect deterministically.
9. Multi-model products need assembly-level fit validation. V4 now provides
   first-class mate/clearance contracts, pair coverage, mesh narrow-phase
   interference evidence, combined STL, mandatory MJCF, and interactive
   previews so the bit-holder body/lid workflow no longer depends on matching
   per-model metadata by convention alone.
10. Assembly validation must make MJCF a required verification artifact, not
    an optional viewer export. The source of truth remains `assembly.json` plus
    measured `assembly_geometry.json`; MJCF is generated and round-tripped
    against that geometry to catch export drift.
11. Humans need a first-class preview artifact, not a pile of JSON paths.
    `preview.html` now embeds STL geometry directly and presents Three.js
    inspection, checks, SVG evidence, MJCF text, measurements, assembly
    explode controls, and per-component isolate/focus controls in one local
    page.
12. Side/top/front/back views are not optional; side view caught a floating lip
   that iso and bbox validation did not make obvious.
13. Two real build123d traps that always come back:
   - `Locations + BuildSketch(Plane.XY)` does not move the sketch plane;
     use `Plane(origin=(x, y, z))` instead.
   - `Box(...).moved(Location(...))` inside `BuildPart` double-adds; use
     `with Locations((x, y, z)): Box(...)`.

Both are documented in `references/build123d-guide.md`.

## Tests

`uv run pytest -v` — currently 192 tests across:

- `test_cli.py` — CLI dispatch
- `test_workspace.py` — init / new / sync / discovery
- `test_runner.py`, `test_stale.py` — build runner + hash cache
- `test_stl.py` — pure-Python STL reader and analysis
- `test_render.py`, `test_section.py` — SVG rendering and section extraction
- `test_preview.py` — local interactive HTML preview generation
- `test_validate.py`, `test_weak_check.py` — post-build validation + weak-check warnings + fix suggestions
- `test_diff.py` — validation history archiving and run diff
- `test_variant.py` — model variant creation and variant-aware build
- `test_probe.py` — probe + scan
- `test_geometry.py` — pure shape primitives (AABB, clearance, accessibility, wall thickness)
- `test_assembly.py` — assembly contracts, transform bans, mate residuals, pair coverage, mesh narrow-phase interference, inter-model clearance, section checks, SVG/STL/MJCF artifacts
- `test_precheck_review.py` — `agentcad precheck` and `agentcad review` integration
- `test_jsonio.py`

## Roadmap delivered

| Milestone | Status | Notes |
|---|---|---|
| V0 — minimal agent loop | ✅ delivered | new / build / measure / render / validate / deliver |
| V1 — geometry observability | ✅ delivered | multi-view render, section SVGs, hash cache, three-axis probe + scan, `agentcad inspect`, debug SVG on failure |
| V2 — design spec standardization | ✅ delivered | check IDs, schema validation, weak-check warnings, Markdown report (`agentcad report`) |
| V2.5 — design-time observability | ✅ delivered (new) | `agentcad precheck`, `agentcad review`, four geometric relation checks, common-error catalog, mandatory TDD prompt |
| V2.6 — design-thinking prompts | ✅ delivered (new) | split references, Discovery Gate, Concept Gate, Design Quality Review, real cable-hook e2e |
| V4 — assembly validation | ✅ delivered | `agentcad assembly init/list/validate/review`, rigid transforms, metadata interface measurement, mate residuals, pair coverage, mesh narrow-phase interference, inter-model clearance, section checks, combined/exploded SVG, combined STL, top-level interactive preview, mandatory MJCF round-trip |
| V4.5 — iteration tooling | ✅ delivered | SVG dimension annotations, validation run diff, model variants, fix suggestions |

Next milestones (V3+) are tracked in [`DESIGN.md`](DESIGN.md).
