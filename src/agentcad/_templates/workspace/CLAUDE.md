# AgentCAD Workspace

You are working in an AgentCAD workspace. Your job is to create and refine CAD
models using the `cad` CLI and build123d geometry library.

## Workflow (11 stages — do NOT skip stages)

Two new stages — **precheck** (before code) and **review** (before deliver) —
exist precisely to catch the failure modes listed below in
"Common Design Errors". Skipping them lets silent bugs pass.

1. **Understand**: read the user request, identify every feature.
2. **Contract**: write `models/<name>/design.json` with features + checks.
   Declare shapes inline for `min_clearance` checks (see below).
3. **Params**: put tunable dimensions in `models/<name>/params.json`.
4. **Precheck**: `cad precheck <name> --json`. This solves the design contract
   *statically* — without building. It catches interferences, schema errors,
   and feature-coverage gaps before you write code. **Do not write part.py
   while precheck fails.**
5. **Implement**: write `models/<name>/part.py` using build123d.
   - Final object MUST be assigned to global variable `result`.
   - Optional `metadata` dict gets written to metadata.json.
6. **Build**: `cad build <name>` (auto-cached unless `--force`).
7. **Measure**: `cad measure <name> --json` for STL geometry stats.
8. **Render**: `cad render <name> --views iso,back` (validate auto-renders).
9. **Validate**: `cad validate <name> --json`. Must be green.
10. **Review**: `cad review <name> --json`. Final pre-delivery checklist —
    pairwise relations matrix, must-view SVGs, missing-check reminders.
    **Do not run `cad deliver` while review fails.**
11. Run `cad deliver <name> --json` ONLY after review passes.

Do NOT manually export STEP/STL from part.py. The runner owns all exports.

## Rules

- Units are millimeters unless the user explicitly says otherwise.
- Coordinate convention: +X right, +Y back, +Z up.
- Do not write generated artifacts outside `models/<name>/outputs/`.
- Treat `design.json` as the design contract — source of truth for what the
  model should be.
- Treat CLI JSON output as the source of truth for what the model actually is.
- Do not claim a model is complete until `cad validate` passes.
- Every requested feature MUST have at least one validation check.
- bbox + watertight alone are NOT sufficient — they pass even when features
  are missing or hidden.

## Workspace Layout

```text
models/<name>/
  design.json    Feature contract: features list + checks
  params.json    Tunable dimensions
  part.py        build123d geometry (assign to `result`)
  metadata.json  (auto-generated if part.py defines `metadata`)
  outputs/
    build.json          Build report
    geometry.json       STL measurement report
    validation.json     Validation results
    deliverable.json    Delivery manifest
    preview.iso.svg     SVG preview
    <name>.step         STEP export
    <name>.stl          STL export
```

## Validation Check Types

| Check type             | What it verifies                                |
|------------------------|-------------------------------------------------|
| bbox_size              | Bounding box dimensions within tolerance        |
| watertight             | STL mesh has no boundary edges                  |
| min_triangles          | Minimum triangle count (catches degenerate)     |
| artifact_exists        | File exists at path (relative to model dir)     |
| metadata_equals        | Value at path in metadata.json matches expected |
| outer_diameter_at_z    | Outer diameter at a Z section plane (supports `center`) |
| inner_diameter_at_z    | Inner diameter at a Z section plane (supports `center`) |
| diameter_decreases_along_z | Diameter monotonically decreases over Z range |
| volume_range           | Volume within min/max bounds                    |
| section_bbox_at_z      | Check an XY region at Z is "solid" or "void"    |
| **min_clearance**      | **Two declared shapes have ≥ N mm edge-to-edge gap** (precheck-able, no STL needed) |
| **hole_accessibility** | **Tool envelope of given radius can reach a hole at Z** (catches buried holes) |
| **min_wall_thickness** | **Min point-pair distance in a region** at Z (catches thin walls)               |
| **feature_position**   | **A point at (x,y,z) is in expected solid/void state**                           |
| feature_coverage       | (auto) Every feature references a check         |

## design.json Example

```json
{
  "schema": "design-spec.v1",
  "model": "bracket",
  "units": "mm",
  "intent": "L-bracket with two mounting holes",
  "features": [
    {
      "id": "base_plate",
      "intent": "Horizontal mounting plate",
      "checks": ["base_bbox", "watertight"]
    },
    {
      "id": "mounting_holes",
      "intent": "Two M4 clearance holes",
      "checks": ["hole_count"]
    }
  ],
  "checks": [
    {"id": "base_bbox",   "type": "bbox_size",      "expected": [60, 40, 5], "tolerance": 0.3},
    {"id": "watertight",  "type": "watertight",      "expected": true},
    {"id": "hole_count",  "type": "min_triangles",   "expected": 100},
    {"id": "step_file",   "type": "artifact_exists", "path": "outputs/bracket.step"},
    {"id": "stl_file",    "type": "artifact_exists", "path": "outputs/bracket.stl"}
  ]
}
```

## Common Design Errors (mandatory pre-design checklist)

Walk this list before writing every design.json. Each error lists a tool that
catches it automatically.

### A. Inter-feature spatial relations (most common, hardest to validate)

| Error | Symptom | How to prevent it |
|---|---|---|
| **Hole-wall interference** (hole edge buried under adjacent solid) | Top-down view shows hole half-covered by a wall, yet `inner_diameter_at_z` still passes | Add a `min_clearance` check: `feature_a` = hole cylinder, `feature_b` = adjacent box. Precheck reports the gap directly. |
| **Hole-edge break** | Hole sits too close to part edge, leaving a C-shaped opening after machining | Add a `min_clearance` check with `feature_b` set to the external bounding box's near edge; verify clearance > 0 |
| **Hole-to-hole punch-through** | Two holes spaced < their diameter apart, so the walls between them open up | Add a `min_clearance` check pairing both hole cylinders with `min_mm = 2 * wall_thickness` |
| **Rib obstructs assembly hole** | Bolt threads in but the wrench cannot turn | Add a `hole_accessibility` check with `clearance_radius` set to the wrench socket radius |
| **center-to-face used instead of edge-to-edge** (the classic human error) | Mental math says "hole_y=15, wall_y=16 ⇒ 1 mm gap", forgetting to subtract the 2.25 mm radius | **Always reason in edges: `hole_center ± hole_radius` must not enter the neighbouring solid's range.** |

### B. Manufacturability

| Error | Symptom | How to prevent it |
|---|---|---|
| **Wall too thin** | FDM print snaps; injection moulding short-shot | Add a `min_wall_thickness` check; the region must cross both wall faces; `min_mm ≥ 1.0` (FDM) or `≥ 0.8` (injection) |
| **Feature smaller than tool radius** | Sharp inner corners cannot be milled; ⌀1 mm holes cannot be drilled | Keep every radius in params.json ≥ 0.5 mm; add fillet radius ≥ 1 mm at sharp inner corners |
| **Undercuts / overhangs** | 3D printing requires support material | Inspect the iso / section SVGs in the review stage |

### C. Assembly and accessibility

| Error | Symptom | How to prevent it |
|---|---|---|
| **No room to drive the bolt** | Socket wrench will not seat | `hole_accessibility` check with `clearance_radius = (bolt_head_outer_diameter / 2) + 1` |
| **Blind hole shallower than the bolt** | Bolt bottoms out | `feature_position` at the bottom of the hole verifies solid; ensure `hole_depth ≥ bolt_length + 1` |
| **Tolerance stack-up** | Three features pass individually but the stack is out of spec | Roll the cumulative tolerance into the `min_mm` of a `min_clearance` check |

### D. Geometric integrity (build123d traps)

| Error | Symptom | How to prevent it |
|---|---|---|
| **`Box(...).moved(Location(...))` double-adds** | The shape appears once at the original location and once at the moved location | **Always use `with Locations((x, y, z)): Box(...)`; never `.moved()` inside a builder context.** |
| **`Locations + BuildSketch(Plane.XY)`** | The sketch stays at Z=0 and never moves to the intended Z | **BuildSketch must use `Plane(origin=(x, y, z))`; an outer `Locations` does not move the sketch plane.** |
| **Zero-volume subtraction** | `Mode.SUBTRACT` cuts nothing | When build fails after precheck passes, run `cad probe --scan` and confirm the `step_changes` match the intended features |
| **Tiny residual sliver** | A 0.001 mm Z-range error leaves a paper-thin shell behind | Add a +0.1 mm overshoot to subtraction radii / depths |

### E. Intent vs. implementation drift

| Error | Symptom | How to prevent it |
|---|---|---|
| **Feature in the wrong direction** (hole drilled the wrong way) | Validate passes but the function is broken | Use `feature_position` to assert a void point along the hole axis, then visually confirm via section SVG |
| **Param field silently ignored** | Editing params.json does not change the model | `print(PARAMS)` at the top of part.py; the effective values land in build.json |
| **bbox passes but interior is wrong** | Outer envelope is correct, hole positions and walls are not | bbox alone is insufficient — every feature needs a section / diameter / clearance check |

### Hard rules (violation ⇒ rewrite design.json)

1. **Every hole needs a `min_clearance` check** for each surrounding wall or adjacent solid.
2. **Reason edge-to-edge, never center-to-face**: clearance must be measured between feature edges, not between centerlines and faces.
3. **Every feature has at least one geometry check** (not just bbox/watertight). Resolve every weak-check warning before proceeding.
4. **Run `cad review` before every `cad deliver`** and visually inspect every entry in `must_view`.

## CAD TDD: mandatory workflow (checks first, geometry second)

**Every feature must have a check that can pass or fail before any geometry
is written. The order is not negotiable.**

### Four questions to answer per feature before coding

For every feature you plan to implement, fill in this table before writing
`part.py`:

| Feature | Shape | Center (cx, cy) | Z slice | Expected value | Check type |
|--------|------|-------------|-----------|------------|-----------|
| Outer shell | rectangle | — | — | [w, h, t] | bbox_size |
| Camera hole | W×H rectangle | (cx, cy) | wall_back/2 | min(W, H) | inner_diameter_at_z |
| Inner cavity | void | center | wall_back+2 | "void" | section_bbox_at_z |
| USB-C port | W×H rectangle | (0, y) | z_mid | min(W, H) | inner_diameter_at_z |

If you cannot fill in all four columns for a feature, you have not thought
it through — **do not start coding**.

### Step 1 — Red phase

After finishing `design.json`, write a minimal `part.py` that produces the
outer envelope only (no internal features) and run:

```bash
cad validate <model> --json
```

Expected outcome:
- `bbox_size` → ✅ passes (outer shell is correct)
- Every section check → ❌ fails (internal features not yet built)

**If a section check passes while its feature is missing, the check is
wrong — return to the table and redesign it.**

### Step 2 — Green phase (one feature at a time)

Implement one feature at a time and rerun `cad validate` immediately to
watch the matching check flip from ❌ to ✅. Do not batch up multiple
features before validating — incremental feedback is the whole point of TDD.

### Feature → Check cheat sheet

| Feature type | Check type | Z slice | Expected value | Tolerance |
|---------|-----------|-----------|--------------|-----------|
| Circular hole ⌀D | inner_diameter_at_z | mid-Z of hole | D | 0.3 |
| Rectangular hole W×H | inner_diameter_at_z | mid-Z of hole | min(W, H) | 3–5 |
| Rectangular void region | section_bbox_at_z expected="void" | mid-Z of feature | — | — |
| Solid face (back panel, boss) | section_bbox_at_z expected="solid" | mid-Z of face | — | — |
| Outer envelope | bbox_size | — | [total_w, d, h] | 0.5 |
| Taper / lead-in | diameter_decreases_along_z | z_range | — | — |
| **Any hole vs. adjacent solid** | **min_clearance** | — | feature_a / feature_b shape descriptors | min_mm=0 |
| **Bolt assembly hole** | **hole_accessibility** | working plane Z of the hole | hole_radius, clearance_radius | — |
| **Thin wall / rib** | **min_wall_thickness** | section Z, region restricted to the wall cross-section | min_mm=1.0 | 0.1 |
| **Direction / position marker** | **feature_position** | point=[x, y, z] | expected="solid"\|"void" | tol=0.5 |

**Z slice formula:** if a feature occupies `[z_bottom, z_top]` along Z, slice
at `z = (z_bottom + z_top) / 2`.

**When you do not know the expected value:** run `cad build`, then
`cad probe <model> --z <z> --json`. The `suggested_checks` field is ready to
paste straight into `design.json`.

**When you do not know which Z to probe:** run `cad probe <model> --scan --json`
to surface step changes (cavity start, wall transitions, etc.) automatically.

## design.json Schema Rules

`cad validate` checks the schema before running any geometry checks. Violations
cause the entire validation to fail with a `design_schema` error.

- **Every check must have a unique `id` field** — even simple checks like `artifact_exists`
- **`type` must be one of the supported check types** (see table above)
- **Feature `checks` arrays reference check ids** — typos will cause `feature_coverage` to fail
- **No duplicate check ids** — each `id` must appear exactly once in `checks`

## Shape Descriptors (used by min_clearance and other relational checks)

Relational checks (`min_clearance`, etc.) consume a unified shape descriptor.
Three shapes are supported, all axis-aligned:

```json
// Cylinder along Z (most common — describes a hole through a plate)
{"type": "cylinder", "axis": "z",
 "center": [-15.0, 15.0], "radius": 2.25,
 "z_range": [0.0, 4.0]}

// Cylinder along Y (describes a transverse hole through an upright wall)
{"type": "cylinder", "axis": "y",
 "center": [0.0, 20.0],   // (cx, cz) for axis=y
 "radius": 2.25,
 "y_range": [16.0, 20.0]}

// Axis-aligned box (describes walls, plates, bosses)
{"type": "box",
 "x_range": [-25.0, 25.0],
 "y_range": [16.0, 20.0],
 "z_range": [0.0, 30.0]}
```

Full `min_clearance` check example:

```json
{
  "id": "left_hole_wall_clearance",
  "type": "min_clearance",
  "feature_a": {"type": "cylinder", "axis": "z",
                "center": [-15.0, 15.0], "radius": 2.25,
                "z_range": [0.0, 4.0]},
  "feature_b": {"type": "box",
                "x_range": [-25.0, 25.0],
                "y_range": [16.0, 20.0],
                "z_range": [0.0, 30.0]},
  "min_mm": 0.0
}
```

The reported `actual_mm` is the **edge-to-edge distance**: negative means
interference, zero means touching, positive means clearance.

`cad precheck` evaluates every `min_clearance` check **before the build
runs**, so the classic "hole edge buried under a wall" bug is caught the
moment design.json is finalised — long before any geometry is generated.

## Validation Strategy

- For axisymmetric features (ducts, sockets, tapers): use `outer_diameter_at_z`
  and `inner_diameter_at_z` at specific Z heights.
- For tapers and chamfers: use `diameter_decreases_along_z` with samples at
  multiple Z values.
- For off-axis holes and rectangular cutouts: use `inner_diameter_at_z` with
  `center` set to the hole/cutout centroid. The inner diameter approximates
  the shortest transverse dimension (e.g., ~`min(W, H)` for a W×H rectangle).
- For solid/void verification of specific rectangular zones: use `section_bbox_at_z`
  with `region: [[x_min,y_min],[x_max,y_max]]` and `expected: "solid"` or `"void"`.
- Tolerance: 0.1-0.2 mm for tight fits, 0.3-0.5 mm for general use, 0.5-1.0 mm
  for non-critical parts. Section check uncertainty is ~0.1 mm.
- ⚠️ `watertight` does NOT confirm a cutout exists — a solid back panel and one
  with a camera hole are both watertight. Always add a section check for cutouts.
- If `validate` output includes a `warnings` array, it means some features have
  only trivial checks (bbox/watertight). Add a section/diameter/bbox check for
  those features. Warnings do not fail validation but should be resolved.
  Use `cad probe` to discover the correct `expected` values.

## Critical build123d Warning

**`Locations(x, y, z) + BuildSketch(Plane.XY) + extrude` does NOT place the
sketch at Z=z.** The sketch always stays on its own plane (Z=0 for Plane.XY),
regardless of any enclosing `Locations` context.

```python
# WRONG — sketch stays at Z=0, inner cavity obliterates back panel
with Locations((0, 0, wall_back)):
    with BuildSketch(Plane.XY):
        RectangleRounded(w, h, r)
    extrude(amount=depth, mode=Mode.SUBTRACT)

# CORRECT — explicit origin positions the plane
with BuildSketch(Plane(origin=(0, 0, wall_back))):
    RectangleRounded(w, h, r)
extrude(amount=depth, mode=Mode.SUBTRACT)
```

Use `Locations` only with 3D primitives (Box, Cylinder, Cone). Use explicit
`Plane(origin=(x, y, z))` for BuildSketch positioning.

## CLI Quick Reference

```bash
cad new <model>                           # Create model (auto-inits workspace)
cad precheck <model> --json               # Static design solve (run BEFORE writing part.py)
cad build <model> --json                  # Build and export STEP/STL (cached if unchanged)
cad build <model> --force --json          # Force rebuild even when source is unchanged
cad measure <model> --json                # Measure STL geometry
cad render <model> --json                 # Generate SVG preview (iso)
cad render <model> --views iso,back --json  # Render multiple views at once
cad validate <model> --json               # Run full validation (auto-renders iso+back)
cad review <model> --json                 # Pre-delivery checklist + relations matrix
cad deliver <model> --json                # Write delivery manifest (only after review passes)
cad probe <model> --z <z> --json                   # Probe Z cross-section (XY plane)
cad probe <model> --z <z> "--center=cx,cy" --json  # Probe Z at off-axis center
cad probe <model> --z <z> --region x0,y0,x1,y1    # Check solid/void in region
cad probe <model> --x <x> --json                   # Probe X cross-section (YZ plane)
cad probe <model> --y <y> --json                   # Probe Y cross-section (XZ plane)
cad probe <model> --scan --json                    # Auto Z-axis profile scan
cad probe <model> --scan --axis x --json           # X-axis scan
cad probe <model> --scan --axis y --json           # Y-axis scan
cad render <model> --section-z <z> --json          # Section SVG at Z height
cad render <model> --section-x <x> --json          # Section SVG at X position (YZ)
cad render <model> --section-y <y> --json          # Section SVG at Y position (XZ)
cad inspect <model> --json                         # Three-axis scan + section SVGs + suggested probes
cad report <model>                                 # Generate Markdown validation report
```

All commands accept `--project <dir>` (defaults to current directory).
All commands accept `--json` for machine-readable output.

### cad probe — Discover expected values before writing design.json

Run `cad probe` AFTER `cad build` and BEFORE filling in `expected` values in
design.json. The output includes `suggested_checks` — ready-to-paste JSON
snippets with actual measured values:

```bash
# Find inner diameter of a camera cutout centred at (-10.3, 53.3) at z=0.75
cad probe my_case "--center=-10.3,53.3" --z 0.75 --json
# → suggested_checks.inner_diameter_at_z.expected = 44.49 (actual measured value)
```

For multiple Z heights in one call (e.g., to profile a taper):
```bash
cad probe my_part --z 2.0,5.0,8.0 --json
```

## Key Resources

Always-on reference docs in `references/` (read them as needed):
- `references/build123d-guide.md` — build123d API reference, patterns, common pitfalls
- `references/validation-strategy.md` — check types, section checks, tolerance, troubleshooting

`references/` is the home for project documentation that should be readable
by both humans and agents throughout the modeling loop.

## Querying build123d Documentation

When you need API details beyond the reference docs (e.g., how to select
edges for fillet, what parameters CounterBoreHole accepts, how Location
arithmetic works), query the build123d documentation directly:

```
WebFetch https://build123d.readthedocs.io/en/latest/<page>.html
```

Key documentation pages:

- **Objects reference**: `objects` — Box, Cylinder, Cone, Sphere, Torus, Wedge
- **Operations**: `operations` — fillet, chamfer, hole, split, mirror, offset
- **Topology selection**: `topology_selection` — filter_by, sort_by, group_by
- **Selectors tutorial**: `tutorial_selectors` — edge/face selection patterns
- **BuildPart**: `build_part` — BuildPart context manager details
- **BuildSketch**: `build_sketch` — 2D sketch construction
- **Moving objects**: `moving_objects` — Location, rotation, alignment
- **Key concepts**: `key_concepts_builder` — Align, Mode, Select enums
- **Cheat sheet**: `cheat_sheet` — quick syntax reference
- **Examples**: `general_examples` — real-world model examples

All URLs follow the pattern:
`https://build123d.readthedocs.io/en/latest/<page>.html`

When stuck on a build123d API question, fetch the relevant page before guessing.
