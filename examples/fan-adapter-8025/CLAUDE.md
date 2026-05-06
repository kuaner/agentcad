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
| outer_diameter_at_z    | Outer diameter at a Z section plane             |
| inner_diameter_at_z    | Inner diameter at a Z section plane             |
| diameter_decreases_along_z | Diameter monotonically decreases over Z range |
| volume_range           | Volume within min/max bounds                    |
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
    {"id": "base_bbox", "type": "bbox_size", "expected": [60, 40, 5], "tolerance": 0.3},
    {"id": "watertight", "type": "watertight", "expected": true},
    {"id": "hole_count", "type": "min_triangles", "expected": 100},
    {"type": "artifact_exists", "path": "outputs/bracket.step"},
    {"type": "artifact_exists", "path": "outputs/bracket.stl"}
  ]
}
```

## Validation Strategy

- For axisymmetric features (ducts, sockets, tapers): use `outer_diameter_at_z`
  and `inner_diameter_at_z` at specific Z heights.
- For tapers and chamfers: use `diameter_decreases_along_z` with samples at
  multiple Z values.
- For off-axis features (bolt holes at corners): `metadata_equals` is a
  placeholder — section checks only work around a single center point.
- Tolerance: 0.1-0.2 mm for tight fits, 0.3-0.5 mm for general use, 0.5-1.0 mm
  for non-critical parts. Section check uncertainty is ~0.1 mm.

## CLI Quick Reference

```bash
cad new <model>                           # Create model (auto-inits workspace)
cad build <model> --json                  # Build and export STEP/STL
cad measure <model> --json                # Measure STL geometry
cad render <model> --json                 # Generate SVG preview
cad validate <model> --json               # Run full validation pipeline
cad deliver <model> --json                # Write delivery manifest
```

All commands accept `--project <dir>` (defaults to current directory).
All commands accept `--json` for machine-readable output.

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
