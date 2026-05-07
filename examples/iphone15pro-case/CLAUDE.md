# AgentCAD Workspace

You are working in an AgentCAD workspace. Your job is to create and refine CAD
models using the `cad` CLI and build123d geometry library.

## Workflow

1. Read the user's request. Identify every visible or functional feature.
2. Write a Feature Contract in `models/<name>/design.json`:
   - List each feature with an id, intent, and linked check ids.
   - Define measurable checks (bbox, diameter, watertight, etc.).
3. Put tunable dimensions in `models/<name>/params.json`.
4. Implement geometry in `models/<name>/part.py` using build123d.
   - The final object MUST be assigned to the global variable `result`.
   - Optional: assign `metadata` dict for design intent that checks can reference.
5. Run `cad validate <name> --json`.
6. If validation fails, read the JSON output, fix the FIRST failing check, and
   rerun validation. Repeat until all checks pass.
7. Run `cad deliver <name> --json` ONLY after validation passes.

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
| feature_coverage       | (auto) Every feature references a check          |

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

## design.json Schema Rules

`cad validate` checks the schema before running any geometry checks. Violations
cause the entire validation to fail with a `design_schema` error.

- **Every check must have a unique `id` field** — even simple checks like `artifact_exists`
- **`type` must be one of the supported check types** (see table above)
- **Feature `checks` arrays reference check ids** — typos will cause `feature_coverage` to fail
- **No duplicate check ids** — each `id` must appear exactly once in `checks`

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
cad build <model> --json                  # Build and export STEP/STL (cached if unchanged)
cad build <model> --force --json          # Force rebuild even when source is unchanged
cad measure <model> --json                # Measure STL geometry
cad render <model> --json                 # Generate SVG preview (iso)
cad render <model> --views iso,back --json  # Render multiple views at once
cad validate <model> --json               # Run full validation (auto-renders iso+back)
cad deliver <model> --json                # Write delivery manifest
cad probe <model> --z <z> --json          # Probe STL cross-section at height Z
cad probe <model> --z <z> "--center=cx,cy" --json  # Probe at off-axis center
cad probe <model> --z <z> --region x0,y0,x1,y1    # Check solid/void in region
cad report <model>                        # Generate Markdown validation report
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

Read the skill files in `skills/` for detailed guidance:
- `build123d-guide.md` — build123d API reference, patterns, common pitfalls
- `validation-strategy.md` — check types, section checks, tolerance, troubleshooting

## Querying build123d Documentation

When you need API details beyond the skill files (e.g., how to select edges for
fillet, what parameters CounterBoreHole accepts, how Location arithmetic works),
query the build123d documentation directly:

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
