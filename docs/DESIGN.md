# AgentCAD Design Document

## 1. Positioning

AgentCAD is an agent-first 3D / CAD modeling workflow runtime. It is not a
traditional CAD UI and not a desktop viewer. Its job is to give coding
agents a repeatable local environment for:

```text
discovery -> concept -> design contract -> precheck -> params/source -> build
          -> measure -> render -> preview -> validate -> review -> quality review -> deliver
```

The user describes a part or assembly; a coding agent creates and refines
the model with minimal manual interaction. Correctness comes from
measurable artifacts, not from visual intuition alone. **Errors must be
catchable at design time whenever possible**, and never accepted
post-build without explicit checks.

## 2. First Principles

### 2.1 Agents already write code

The project does not compete with coding agents. Agents can already edit
files and run shell commands. AgentCAD provides the missing workflow
runtime:

- a stable workspace protocol
- deterministic build / export commands
- structured error reports
- geometry measurements
- preview artifacts, including local interactive HTML review pages
- a typed validation contract
- a delivery manifest

### 2.2 CAD correctness must be observable

CAD is precise. A successful run always produces machine-readable
evidence:

- `precheck.json`
- `build.json`
- `geometry.json`
- `validation.json`
- `observability.json`
- `review.json`
- `deliverable.json`
- preview SVGs (iso, front, top, side, back)
- section SVGs at meaningful Z / X / Y planes
- section measurement sidecars next to every section SVG
- `preview.html` for STL inspection, checks, measurements, and assembly review
- STEP / STL artifacts

### 2.3 Catch errors at the earliest layer that can see them

Layered defense:

| Layer | Tool | What it sees |
|---|---|---|
| Design-time | `agentcad precheck` | Schema, feature coverage, declarative shape clearance. No STL. |
| Build-time | `agentcad build` | Source executes, STEP / STL export, hash cache |
| Post-build | `agentcad measure`, `agentcad probe`, `agentcad inspect` | Mesh facts (bbox, watertight, sections, voids) |
| Validation | `agentcad validate` | All declared checks; auto debug SVGs on failure |
| Pre-delivery | `agentcad review` | Pairwise relations matrix, must-view SVGs, gap detection |

A bug that can be caught at design time **must** be caught there.
Pushing checks downstream when a static solver could have caught them is
treated as a regression of the workflow itself.

### 2.4 CLI first

The core interface is CLI. Coding agents, developers, and CI all consume
it. Every command supports stable JSON output. UI, MCP, and richer
viewers are optional integrations, not core requirements.

## 3. Workspace Protocol

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
    <name>/
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
        debug.<check_id>.{x,y,z}{value}.svg
        <name>.step
        <name>.stl
      outputs/<variant>/
        (same structure, variant-specific)
```

V0 intentionally avoids a project-root `outputs/` directory: each model
owns one unambiguous artifact location.

## 4. Agent Workflow

The mandatory thirteen-stage flow (drilled into `CLAUDE.md` and the workspace
templates):

```text
1.  Read user requirements; run the Discovery Gate when inputs are ambiguous.
2.  For non-trivial parts, compare topology concepts and choose one.
3.  Capture the chosen concept as features and checks in design.json.
4.  Plan checks per feature (the CAD TDD table).
5.  Run `agentcad precheck` to confirm schema + feature coverage + clearance.
6.  Implement params.json (tunable dimensions only).
7.  Implement part.py (incrementally: red -> green per feature).
8.  Run `agentcad validate` after each feature; expect the matching check to
    flip from red to green.
9.  Run `agentcad probe --scan` and `agentcad inspect` to discover step changes
    and confirm internal structure matches intent.
10. Run `agentcad render` for must-view sections plus
    iso/front/top/side/back previews.
11. Run `agentcad review` to inspect the pairwise relations matrix and the
    must-view SVG list.
12. Run the Design Quality Review; revise if the model is valid but not good.
13. Run `agentcad deliver` only after review and quality review pass.
```

Agents must not manually export STEP / STL from `part.py`; the runner
owns exports and reports.

## 5. Modeling Interface

V0 uses build123d source mode. The contract is the source of truth for
intent; the geometry is the implementation.

```text
models/<name>/part.py     -> assigns to global `result`
models/<name>/params.json -> tunable values
models/<name>/design.json -> design intent + validation checks
```

Example contract with both mesh-level and relational checks:

```json
{
  "schema": "design-spec.v1",
  "model": "bracket",
  "units": "mm",
  "intent": "L-shaped mounting bracket",
  "features": [
    { "id": "base_plate",   "description": "horizontal mounting plate" },
    { "id": "upright_wall", "description": "vertical upright wall" },
    { "id": "base_holes",   "description": "M4 base holes" }
  ],
  "checks": [
    { "id": "bbox", "type": "bbox_size",
      "expected": [40, 30, 20], "tolerance": 0.5,
      "feature_ref": "base_plate" },

    { "id": "watertight", "type": "watertight", "expected": true },

    { "id": "left_hole_dia", "type": "inner_diameter_at_z",
      "z": 2.0, "center": [-15, 13], "expected": 4.5, "tolerance": 0.3,
      "feature_ref": "base_holes" },

    { "id": "left_hole_clearance", "type": "min_clearance",
      "feature_a": { "type": "cylinder", "axis": "z",
                     "center": [-15, 13], "radius": 2.25,
                     "z_range": [0, 4] },
      "feature_b": { "type": "box",
                     "x_range": [-25, 25], "y_range": [16, 20],
                     "z_range": [0, 30] },
      "min_mm": 0.0,
      "feature_ref": "base_holes" }
  ]
}
```

`design.json` is a typed contract, not a complete CAD IR. It records
intent and checks that can be evaluated either statically (relational
checks) or after build (mesh-level checks). The delivered feature-helper
library fills the repeated-pattern gap with Python functions that can
register features and checks through `ContractBuilder`; it is still not a
separate declarative CAD DSL.

## 6. CLI Commands

```bash
agentcad init <workspace> [--model <model>]                          # scaffold workspace (and optional first model)
agentcad new <model>                                      # add model in existing workspace
agentcad new <model>:<variant>                            # create variant (same part.py, different params)
agentcad sync [--dry-run] [--only <path>] [--prune-deprecated]  # refresh templates
agentcad precheck <model>                         # design-time solve
agentcad build <model>[:<variant>] [--force]              # part.py -> STEP + STL
agentcad measure <model>[:<variant>]                      # mesh stats + structural facts
agentcad render <model> --view iso                # iso/front/top/side/back
agentcad render <model> --views iso,front,top     # multiple views in one run
agentcad render <model> --section-z|x|y <v>              # cross-section SVG + measurement JSON
agentcad validate <model>[:<variant>] [--views iso,front,top]  # full pipeline with fix suggestions
agentcad diff <model> [--last]                             # compare validation runs
agentcad review <model>                           # pre-delivery checklist
agentcad deliver <model>[:<variant>]                      # delivery manifest
agentcad preview <name>[:<variant>] [--kind model|assembly]  # interactive HTML preview
agentcad probe <model> --z|--x|--y <v>            # cross-section diameters + section analysis
agentcad probe <model> --z <v> --cx <x> --cy <y>  # radial center aliases
agentcad probe <model> --z <v> --line-u <u>       # active line measurement in section axes
agentcad probe <model> --z <v> --point u,v        # nearest contour distance in section axes
agentcad probe <model> --scan --axis x|y|z        # axis profile + step changes
agentcad inspect <model>                          # three-axis scan + sections + suggested probes
agentcad report <model>                                  # Markdown summary
```

Failures return JSON containing `stage`, `error.type`, `error.message`,
and relevant artifact paths.

## 7. Implementation Stack

- `build123d` for CAD construction and STEP / STL export.
- Pure-Python STL parsing for measurement (no `numpy-stl` dependency).
- Dependency-free SVG renderer for previews and cross-sections.
- Local Three.js preview generator for model and assembly artifact review.
- Pure shape primitives (`agentcad/geometry.py`) for design-time
  relational checks (no STL needed).
- `agentcad.features` helper library and `agentcad.hardware` dimension tables
  for reusable CAD primitives that can emit validation contracts.
- JSON reports for every stage.

## 7.1 E2E Lessons Folded Back Into The Runtime

The real cable-hook e2e exposed two workflow failures that ordinary validation
could miss:

1. A model can be valid and still use the wrong topology. The fix is the
   concept gate plus mandatory orthographic preview review.
2. A feature can exist and still be functionally detached. The fix is to
   require root/interface checks for load-bearing attached features, not just
   body-exists checks.

Runtime consequences:

- `agentcad validate` renders all five core previews by default.
- `agentcad review` lists iso/front/top/side/back as required `must_view`
  artifacts, so a side-view floating feature cannot be ignored.
- `hole_accessibility` supports X/Y/Z approach axes and review blocks declared
  holes that lack access-envelope checks.

The SVG renderer is intentionally modest. It gives agents and humans a
deterministic preview artifact without requiring Blender, Playwright, or a
GUI. Interactive HTML previews are delivered for local review; PNG and glTF
remain optional future export formats.

## 8. Iteration Plan

### V0 — Minimal agent loop ✅ delivered

- workspace + model scaffolds
- build123d runner, STEP / STL export
- STL measurement + SVG preview
- validation report + delivery manifest

### V1 — Geometry observability ✅ delivered

- multi-view rendering (iso / front / top / side / back)
- topology-aware mesh statistics
- artifact hashes + stale build detection
- three-axis probe (`--z / --x / --y`) and `--scan` profile
- `agentcad inspect`: three-axis scan + auto sections + suggested probes
- automatic debug SVGs on failed section checks

### V2 — Design spec standardization ✅ delivered

- check `id` field and unique-id validation
- design schema validator
- weak-check warnings (a feature with only `bbox_size` / `watertight`
  flags as weak)
- `feature_coverage` automatic check
- Markdown report (`agentcad report`)

### V2.5 — Design-time observability ✅ delivered

- `agentcad/geometry.py`: pure shape primitives
- four geometric-relation checks: `min_clearance`,
  `hole_accessibility`, `min_wall_thickness`, `feature_position`
- `agentcad precheck` — static design-time solver
- `agentcad review` — pre-delivery checklist with pairwise relations matrix
  and must-view SVG list
- common-error catalog and mandatory TDD red-green workflow encoded in
  the `CLAUDE.md` template

### V3 — Feature library ✅ delivered

Status: delivered. Repeated primitives across the fan-adapter, phone-case,
mounting-bracket, drone-panel, gear-housing, and pipe-coupling examples are now
covered by `agentcad.features`.

Delivered surface:

- `ContractBuilder` accumulates feature/check records and can merge them into
  `models/<name>/design.json`.
- Core helpers cover plates, bosses, ribs, slots, tubes, rectangular tubes,
  wedges, prismoids, torus rings, pie slices, chamfer/rounding masks, screw
  holes, stepped bores, mounting patterns, nut traps, threaded rods/nuts,
  screws, duct sockets, living hinges, dovetails, hex panels, snap pins,
  sparse walls, NEMA mounts, knurls, spur gears, and ring gears.
- `agentcad.hardware` provides screw, nut, washer, and heat-set insert lookup
  data for hardware-driven helpers.
- `tests/test_features/` verifies helper geometry and emitted contract checks;
  helper-driven examples include `e2e-feature-demo`, `e2e-feature-helpers`,
  `drone-panel`, `gear-housing`, and `pipe-coupling`.

The library intentionally remains a Python helper layer. A declarative feature
DSL is still deferred until helper composition shows a concrete need.

### V4 — Assembly + relations

- Delivered: `agentcad assembly init/list/validate/review`
- assembly workspace convention (`assemblies/<name>/assembly.json`)
- rigid component transforms with assembly-level scale rejected
- metadata anchors/interfaces resolved from component `metadata.json`
- mate residuals for coincident, axis-aligned, coaxial, and axial engagement
- radial clearance, assembly bbox, pair coverage, descriptor clearance,
  assembly section count, and mesh narrow-phase interference checks
- mandatory MJCF export plus round-trip consistency check against measured
  assembly geometry
- combined transformed assembly STL export
- interactive local `preview.html` for model and assembly review
- top-level `agentcad preview <name>` regenerates either model or assembly
  previews; assembly remains an optional workflow layer, not the owner of
  preview
- OCCT/MuJoCo remain optional external viewer runtimes; AgentCAD validation is
  decided by JSON contracts, measured geometry, STL evidence, and MJCF
  consistency

### V4.5 — Iteration tooling

- SVG dimension annotations on all preview SVGs: axis labels, dimension lines
  with mm values, and scale bar. Applies to both model and assembly SVGs.
- Validation run diff: `agentcad diff <model>` compares current vs previous
  validation run, classifying checks as fixed/regressed/stable/new/removed with
  geometry drift detection.
- Model variants: `agentcad new <model>:<variant>` creates a variant with
  its own `params.json`; `model:variant` syntax on any command
  (build/validate/preview/deliver) routes to variant-specific output directories
  while sharing the same `part.py` and `design.json`.
- Fix suggestions: failing checks get `suggested_fix` objects with actionable
  guidance. Checks with `param_ref` produce param-targeted fixes with confidence
  levels; checks without get generic action strings.

### V5 — CAD CI partially delivered

- Delivered: GitHub Actions fast suite on pushes/PRs, scheduled/manual slow
  test workflow, PyPI publish workflow with CI verification.
- Planned: `agentcad validate all`
- Planned: regression snapshots for STEP / STL hashes and validation outputs
- Planned: batch model generation
- Planned: benchmark suite (build time, validation time, mesh size)

### V6 — Optional integrations (kept out of the core loop)

- MCP server exposing the same CLI surface
- richer 3D snapshots (PNG / glTF) generated on demand
- external viewer handoff beyond generated HTML previews

## 9. Open design questions

1. **When does a helper layer become a DSL?** V3 deliberately chose Python
   helpers over a declarative feature schema. Revisit only if helper
   composition becomes hard to validate or reason about.
2. **Does `metadata.json` deserve a schema?** It is currently free-form.
   Assembly interfaces already rely on metadata shape references, so a stricter
   schema may be warranted.
3. **What is the next preview format?** Interactive HTML and SVGs are
   delivered. PNG / glTF should be added only if CI artifacts or downstream
   review workflows need them.
