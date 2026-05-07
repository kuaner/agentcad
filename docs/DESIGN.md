# AgentCAD Design Document

## 1. Positioning

AgentCAD is an agent-first 3D / CAD modeling workflow runtime. It is not a
traditional CAD UI and not a desktop viewer. Its job is to give coding
agents a repeatable local environment for:

```text
design contract -> precheck -> params/source -> build
                  -> measure -> render -> validate -> review -> deliver
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
- preview artifacts
- a typed validation contract
- a delivery manifest

### 2.2 CAD correctness must be observable

CAD is precise. A successful run always produces machine-readable
evidence:

- `precheck.json`
- `build.json`
- `geometry.json`
- `validation.json`
- `review.json`
- `deliverable.json`
- preview SVGs (iso, front, top, side, back)
- section SVGs at meaningful Z / X / Y planes
- STEP / STL artifacts

### 2.3 Catch errors at the earliest layer that can see them

Layered defense:

| Layer | Tool | What it sees |
|---|---|---|
| Design-time | `cad precheck` | Schema, feature coverage, declarative shape clearance. No STL. |
| Build-time | `cad build` | Source executes, STEP / STL export, hash cache |
| Post-build | `cad measure`, `cad probe`, `cad inspect` | Mesh facts (bbox, watertight, sections, voids) |
| Validation | `cad validate` | All declared checks; auto debug SVGs on failure |
| Pre-delivery | `cad review` | Pairwise relations matrix, must-view SVGs, gap detection |

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
  skills/
    build123d-guide.md
    validation-strategy.md
  references/
    images/
    notes.md
  models/
    <name>/
      README.md
      design.json
      params.json
      part.py
      metadata.json
      outputs/
        precheck.json
        build.json
        geometry.json
        validation.json
        review.json
        deliverable.json
        preview.{iso,front,top,side,back}.svg
        section.{x,y,z}{value}.svg
        debug.<check_id>.{x,y,z}{value}.svg
        <name>.step
        <name>.stl
```

V0 intentionally avoids a project-root `outputs/` directory: each model
owns one unambiguous artifact location.

## 4. Agent Workflow

The mandatory ten-stage flow (drilled into `CLAUDE.md` and the workspace
templates):

```text
1.  Read user requirements; capture them as features in design.json.
2.  Plan checks per feature (the four-question table for TDD).
3.  Run `cad precheck` to confirm schema + feature coverage + clearance.
4.  Implement params.json (tunable dimensions only).
5.  Implement part.py (incrementally: red -> green per feature).
6.  Run `cad validate` after each feature; expect the matching check to
    flip from red to green.
7.  Run `cad probe --scan` and `cad inspect` to discover step changes
    and confirm internal structure matches intent.
8.  Run `cad render` for must-view sections and the iso preview.
9.  Run `cad review` to inspect the pairwise relations matrix and the
    must-view SVG list.
10. Run `cad deliver` only after `review` passes.
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
checks) or after build (mesh-level checks). A feature library or DSL is
introduced only when repeated patterns justify it (V3+).

## 6. CLI Commands

```bash
cad new <model>                                     # scaffold + auto-init
cad sync                                            # refresh templates
cad precheck <model> --json                         # design-time solve
cad build <model> --json                            # part.py -> STEP + STL
cad measure <model> --json                          # mesh stats + structural facts
cad render <model> --view iso --json                # iso/front/top/side/back
cad render <model> --section-z|x|y <v>              # cross-section SVG
cad probe <model> --z|--x|--y <v> --json            # cross-section diameters
cad probe <model> --scan --axis x|y|z --json        # axis profile + step changes
cad inspect <model> --json                          # three-axis scan + sections + suggested probes
cad validate <model> --json                         # full pipeline
cad review <model> --json                           # pre-delivery checklist
cad deliver <model> --json                          # delivery manifest
cad report <model>                                  # Markdown summary
```

Failures return JSON containing `stage`, `error.type`, `error.message`,
and relevant artifact paths.

## 7. Implementation Stack

- `build123d` for CAD construction and STEP / STL export.
- Pure-Python STL parsing for measurement (no `numpy-stl` dependency).
- Dependency-free SVG renderer for previews and cross-sections.
- Pure shape primitives (`agentcad/geometry.py`) for design-time
  relational checks (no STL needed).
- JSON reports for every stage.

The SVG renderer is intentionally modest. It gives agents and humans a
preview artifact without requiring Blender, Three.js, Playwright, or a
GUI. PNG, GLTF, and interactive viewers are future enhancements.

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
- `cad inspect`: three-axis scan + auto sections + suggested probes
- automatic debug SVGs on failed section checks

### V2 — Design spec standardization ✅ delivered

- check `id` field and unique-id validation
- design schema validator
- weak-check warnings (a feature with only `bbox_size` / `watertight`
  flags as weak)
- `feature_coverage` automatic check
- Markdown report (`cad report`)

### V2.5 — Design-time observability ✅ delivered

- `agentcad/geometry.py`: pure shape primitives
- four geometric-relation checks: `min_clearance`,
  `hole_accessibility`, `min_wall_thickness`, `feature_position`
- `cad precheck` — static design-time solver
- `cad review` — pre-delivery checklist with pairwise relations matrix
  and must-view SVG list
- common-error catalog and mandatory TDD red-green workflow encoded in
  the `CLAUDE.md` template

### V3 — Feature library (next)

Status: planned. Triggered by repeated patterns observed across the
fan-adapter, phone-case, and mounting-bracket examples.

Goal: short, declarative helpers for frequent CAD primitives, each one
auto-emitting matching feature + check entries into `design.json`.

Initial set:

- `plate(w, d, t, fillet?)`
- `mounting_pattern(spec)` — square / rectangular bolt patterns with
  through-holes, counterbores, countersinks
- `boss(d, h)`
- `rib(start, end, t, h)`
- `slot(...)`
- `stepped_bore(...)` — through-hole + head recess + magnet pocket
- `duct_socket(od, length, lead_in)`

Each helper writes:

- a feature record into `design.json`
- a default set of checks (bbox, inner-diameter, section, clearance vs
  declared neighbours)
- a `metadata` entry recording the helper invocation

Acceptance: existing examples can be rewritten using helpers with no
loss of validation strength.

### V4 — Assembly + relations

- assembly workspace convention (multiple models, shared references)
- anchors and mate points
- inter-model `min_clearance`, `hole_accessibility` (cross-references)
- collision check based on STL / mesh
- optional MJCF / URDF / glTF export for kinematic preview

### V5 — CAD CI

- `cad validate all`
- regression snapshots for STEP / STL hashes and validation outputs
- batch model generation
- benchmark suite (build time, validation time, mesh size)
- GitHub Actions example

### V6 — Optional integrations (kept out of the core loop)

- MCP server exposing the same CLI surface
- live-preview viewer (Three.js / glTF) when section SVG is insufficient
- richer 3D snapshots (PNG / glTF) generated on demand

## 9. Open design questions

1. **DSL vs. helpers?** V3 chooses helpers (Python functions returning
   build123d shapes, with side effects on `design.json`) over a full
   declarative DSL. Revisit if helpers fail to compose well.
2. **How many examples is enough?** Three is the current minimum
   (fan-adapter, phone-case, mounting-bracket). V3 adds at least one
   assembly example to drive helper-library design.
3. **Does `metadata.json` deserve a schema?** It is currently free-form.
   If `metadata_equals` checks proliferate, a schema may be warranted.
4. **PNG export for review?** Not required for V3. Reconsider once
   helpers and assemblies make section SVGs inadequate.

