# AgentCAD Roadmap

Last updated: 2026-05-07

This document is the actionable companion to [`DESIGN.md`](DESIGN.md). It
takes the high-level milestones (V0 – V6) and breaks them into concrete,
sequenced engineering tasks with explicit acceptance criteria. The
ordering reflects current priorities; stages are independent enough that
ordering can be revisited at the start of each milestone.

For background on what is already shipped, see
[`STATUS.md`](STATUS.md).

## Milestone overview

| Milestone | Theme | Status | Headline outcome |
|---|---|---|---|
| V0 | Minimal agent loop | ✅ delivered | new / build / measure / render / validate / deliver |
| V1 | Geometry observability | ✅ delivered | three-axis probe + scan, multi-view, debug SVGs |
| V2 | Design spec standardization | ✅ delivered | check IDs, schema, weak-check warnings, Markdown report |
| V2.5 | Design-time observability | ✅ delivered | `precheck`, `review`, four relational checks, common-error catalog |
| **V3** | **Feature library** | **next** | **declarative helpers that emit matching checks** |
| V4 | Assembly + relations | planned | multi-model workspace, mate points, inter-model clearance |
| V5 | CAD CI | planned | `validate all`, regression snapshots, GitHub Actions |
| V6 | Optional integrations | deferred | MCP server, live viewer, PNG / glTF previews |

## V3 — Feature library

### Why now

Across the existing examples we already see the same primitives written
by hand multiple times:

- the fan-adapter has a 71.5 mm bolt pattern;
- the magnetic outlet plate has the same pattern plus stepped bores;
- the mounting bracket repeats two M4 through-holes;
- the iPhone case has rounded plates with multiple rectangular cutouts.

Every one of these required the agent to write the geometry **and** to
write the matching checks (`bbox_size`, `inner_diameter_at_z`,
`min_clearance`, `hole_accessibility`). The check side is mechanical and
prone to omission. Helpers can write both halves at once.

### Scope

Exposed as a thin `agentcad.features` module that returns build123d
objects **and** mutates the model's `design.json` to add matching feature
+ check entries.

Initial helper set:

| Helper | Geometry | Auto-emitted checks |
|---|---|---|
| `plate(w, d, t, fillet=0)` | rounded plate | `bbox_size` |
| `mounting_pattern(spacing, hole_d, plate_thickness, offsets)` | array of through-holes | one `inner_diameter_at_z` per hole + `min_clearance` to plate edges |
| `boss(d, h, position)` | cylindrical boss | `outer_diameter_at_z` at top + `feature_position` solid at top center |
| `rib(start, end, t, h)` | rectangular rib | `min_wall_thickness` across the rib + `feature_position` solid at midpoint |
| `slot(length, width, depth, position)` | rounded slot | `inner_diameter_at_z` at slot center + `min_clearance` vs neighbours |
| `stepped_bore(through_d, head_d, head_depth, plate_thickness, position)` | counterbore stack | per-step `inner_diameter_at_z` + `feature_position` chain |
| `duct_socket(od, length, lead_in)` | cylindrical socket with chamfer | `outer_diameter_at_z` at top + `diameter_decreases_along_z` for the lead-in |

Each helper:

- accepts a `name` argument that becomes both the build123d label and
  the `feature_id` in `design.json`;
- accepts an optional `neighbours` list (other declared shape
  descriptors) and emits `min_clearance` checks against each;
- writes its invocation arguments to `metadata.json` so the part can
  later be reasoned about declaratively.

### Deliverables

1. `src/agentcad/features/__init__.py` — public helper API.
2. `src/agentcad/features/_emit.py` — internal utility to merge
   feature + check entries into `design.json` (idempotent on re-build).
3. `tests/test_features.py` — unit + integration tests per helper:
   - building a single helper produces the expected geometry hash;
   - the matching checks pass against the resulting STL;
   - re-running `cad build` does not duplicate feature / check entries
     in `design.json`.
4. `examples/feature-library/` — a minimal showcase model exercising
   every helper.
5. Rewrite at least one existing example (recommended:
   `fan_duct_adapter_8025`) using helpers; show the diff in the
   pull request and document line savings + check coverage parity.
6. `references/build123d-guide.md` and `references/validation-strategy.md` updated
   with helper usage patterns.

### Acceptance criteria

- All seven helpers ship with tests.
- Helpers fail loudly (raise) when invoked with parameters that would
  produce a `min_clearance` violation against a declared neighbour, so
  errors surface during `cad build` rather than `cad validate`.
- `cad precheck` on a helper-driven model passes without manual
  authoring of `design.json` checks beyond features the helpers do not
  cover.
- The rewritten fan-adapter has the same or stronger validation than
  the hand-written version (no regression in `validation.json`).

### Open questions

- Should helpers also emit `metadata` entries that `metadata_equals`
  checks can target? (Lean: yes, for assembly-direction features.)
- Where to draw the line between "helper" and "DSL"? Helpers stay
  Python functions; if a declarative `features:` array starts to
  emerge, V4 can promote it into a real schema.

### Estimated effort

Roughly two implementation chunks: primitives (`plate`, `boss`,
`mounting_pattern`, `slot`) and stacked / extruded helpers
(`rib`, `stepped_bore`, `duct_socket`). Plus one chunk for the
showcase example and the fan-adapter rewrite.

---

## V4 — Assembly + relations

### Why

V3 makes single parts cheap to author. The next ceiling is multi-part
assemblies: most real CAD work is "this part bolts to that part with X
clearance and Y mate". Today an agent has to reason about two STL files
in two different model directories with no shared coordinate system.

### Scope

- `cadproject.json` gains an optional `assemblies:` array. Each
  assembly references models by name, supplies a transform per model,
  and a list of mate points.
- New CLI:
  - `cad assembly init <name>` — scaffold an assembly directory.
  - `cad assembly validate <name>` — run inter-model
    `min_clearance` / `hole_accessibility` / `feature_position` checks.
  - `cad assembly render <name> --view iso|exploded` — render combined
    SVG / glTF preview.
- Inter-model relational checks: the existing four geometric-relation
  checks gain a `feature_a_model` / `feature_b_model` syntax so they can
  reference shapes declared in two different models.
- Optional MJCF / URDF export for kinematic experimentation.

### Acceptance

- A new example `examples/fan-with-screen/` combines the existing
  `fan_duct_adapter_8025` and `outlet_magnetic_screen_plate_8025` into
  an assembly with mate points and pass an inter-model
  `min_clearance` check.

---

## V5 — CAD CI

- `cad validate all` walks every model in the workspace.
- Regression snapshots: hash STEP / STL outputs and store
  `validation.json`; PRs that change either are flagged.
- Benchmark suite: tracks build time, validation time, mesh size
  per example.
- GitHub Actions sample workflow under `examples/.github/`.

### Acceptance

- A red-vs-green PR demo where a helper change causes one example's
  mesh hash to drift; CI flags the regression and the diff is
  human-reviewable.

---

## V6 — Optional integrations (deferred)

Kept out of the core loop on purpose. Pick up only when the CLI
+ JSON contract is no longer enough.

- MCP server exposing the same CLI surface (so non-CLI agents can
  drive AgentCAD).
- Live preview viewer (Three.js + glTF) when section SVGs prove
  inadequate.
- PNG / glTF / STEP-AP242 export.
- Template gallery (browse-and-fork existing models).

---

## Cross-cutting tasks (any milestone)

These are smaller items that can be done at any point; group them into
PRs alongside whichever milestone they support.

- **Section semantics**: today's `section_bbox_at_z` `expected: "void"`
  treats any empty intersection as a void. Tighten by requiring the
  `region` argument when the model is hollow, so a missed mesh
  slice does not silently pass.
- **Probe ergonomics**: `cad probe --center=-10,5` requires the `=`
  workaround for negative numbers. Add `--cx -10 --cy 5` aliases.
- **Render speed**: section SVG rendering on the iPhone case takes
  >1 s; profile and cache the triangle-plane intersection.
- **`cad sync` diff mode**: today `cad sync` overwrites template files;
  add `--dry-run` to print a diff and `--only <path>` to update one
  file.
- **`min_wall_thickness` 3D mode**: today the check works on a single Z
  slice. Extend with a Z-range option that takes the worst slice.
- **Common-error regression tests**: each catalogued common error
  (hole-wall interference, hole-edge break, hole-to-hole, rib blocking
  bolt) gets a fixture model that *should* fail validation, plus a
  test that asserts validation fails for the right reason.

---

## Decision log (recent)

| Date | Decision | Why |
|---|---|---|
| 2026-05-07 | Treat the four geometric-relation checks as design-time first, post-build second | The original interference bug was a hand-math error in `design.json`; catching it post-build is too late and re-runs cost agent context. |
| 2026-05-07 | Make `precheck` and `review` mandatory checkpoints | The mounting-bracket E2E run only surfaced the hole-wall interference because we manually inspected the iso preview. Reviewing must be cheap and routine. |
| 2026-05-07 | All workspace docs are English-only | Mixed-language templates were confusing for agents that translate selectively; English is the lingua franca. |
| 2026-05-06 | Helpers (V3) over a declarative DSL | A DSL forces upfront design choices we have not learned yet; helpers compose freely and emit matching checks today. |
| 2026-05-06 | No project-root `outputs/` directory | Each model owns its artifacts; ambiguity caused stale-artifact bugs in early V0. |

---

## How to keep this document accurate

- After every milestone PR, update the table in
  [Milestone overview](#milestone-overview) and the corresponding
  STATUS.md milestone block.
- Add a row to the [Decision log](#decision-log-recent) whenever a
  major roadmap question is settled.
- Open questions for an in-flight milestone live under that milestone's
  "Open questions" subsection, not in the global section.
