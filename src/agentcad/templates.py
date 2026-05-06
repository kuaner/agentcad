from __future__ import annotations

import json


CADPROJECT_JSON = {
    "schema": "agentcad.project.v1",
    "units": "mm",
    "modelsDir": "models",
    "referencesDir": "references",
    "defaultBackend": "build123d",
}


WORKSPACE_CLAUDE_MD = """# AgentCAD Workspace

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
- `build123d-guide.md` — build123d patterns, common features, pitfalls
- `validation-strategy.md` — check type selection, section checks, tolerance
- `common-errors.md` — build errors, validation failures, modeling pitfalls
"""


SKILL_BUILD123D_GUIDE = """# build123d Modeling Guide

## Imports

```python
from build123d import *
```

This imports all geometry builders (Box, Cylinder, Sphere, etc.), context
managers (BuildPart, BuildSketch, BuildLine), and operations (fillet, chamfer,
hole, split, mirror, etc.).

## Core Pattern

```python
with BuildPart() as bp:
    # start with a base solid
    add(Box(length, width, height))
    # subtract or add features
    with Locations(some_positions):
        CounterBoreHole(radius, depth, cbore_radius, cbore_depth)
result = bp.part
```

Every part.py must assign the final geometry to the global variable `result`.

## Common Features

### Holes and Bore Patterns

```python
# Simple through hole
Hole(radius=2.25)

# Countersunk hole (flat-head screw)
CounterSinkHole(radius=2.25, counter_sink_radius=4.5, counter_sink_angle=82)

# Counterbored hole (socket-head screw)
CounterBoreHole(radius=2.25, depth=3.0, counter_bore_radius=4.3, counter_bore_depth=3.0)

# Rectangular hole pattern
with GridLocations(x_spacing, y_spacing, x_count, y_count):
    Hole(radius=2.25)

# Circular hole pattern
with PolarLocations(radius, count):
    Hole(radius=2.25)
```

### Bosses and Pockets

```python
# Raised boss
with BuildPart() as bp:
    add(Box(50, 50, 5))
    with Locations((0, 0, 0)):
        add(Cylinder(radius=5, height=10))
result = bp.part

# Pocket / pocket hole
with BuildPart() as bp:
    add(Box(50, 50, 10))
    with Locations((0, 0, 5)):
        CounterBoreHole(0, 0, 8.5, 2.0)  # subtracts from top
result = bp.part
```

### Fillets and Chamfers

```python
with BuildPart() as bp:
    add(Box(30, 30, 10, align=(Align.CENTER, Align.CENTER, Align.MIN)))
    # Fillet top edges
    fillet(bp.edges().filter_by(Axis.Z)[-4:], radius=3)
    # Chamfer bottom edges
    chamfer(bp.edges().filter_by(Axis.Z)[:4], length=1)
result = bp.part
```

Select edges carefully. `filter_by(Axis)` picks edges parallel to that axis.
Use edge selectors BEFORE boolean operations that might destroy the edges you
want to fillet.

### Tubes and Sockets

```python
# Solid tube (cylinder with axial hole)
with BuildPart() as bp:
    add(Cylinder(radius=outer_r, height=length))
    with Locations((0, 0, length / 2)):
        Hole(radius=inner_r, depth=length)
result = bp.part

# Male socket (slip-fit)
socket_od = target_id - 0.6  # 0.3 mm radial clearance per side
```

### Flanges and Adapters

```python
# Square flange with bolt holes
with BuildPart() as bp:
    add(Box(flange_w, flange_w, flange_h))
    with GridLocations(mount_spacing, mount_spacing, 2, 2):
        Hole(radius=screw_r)
result = bp.part
```

## Boolean Operation Pitfalls

### Overlapping solids hide features

If you add a cylinder that overlaps a chamfer, the chamfer is still in the
geometry but not visible. BBox and watertight checks pass but the feature does
not function. Always use section checks to verify tapers and chamfers.

### Operation order matters

```python
# WRONG: fillet after hole may fail because edge topology changed
with BuildPart() as bp:
    add(Box(30, 30, 10))
    Hole(radius=5)
    fillet(bp.edges()[-4:], radius=2)  # may pick wrong edges

# RIGHT: fillet first, then subtract
with BuildPart() as bp:
    add(Box(30, 30, 10))
    fillet(bp.edges().filter_by(Axis.Z)[-4:], radius=2)
    Hole(radius=5)
```

### Subtract before adding can leave voids

Always build the base solid first, then subtract (holes, pockets), then add
(bosses). Mixing add and subtract without care can create non-manifold geometry.

## Coordinate Convention

- +X right, +Y back, +Z up
- `Align.MIN` = negative side, `Align.CENTER` = centered, `Align.MAX` = positive side
- Default alignment for Box is `Align.CENTER` on all axes
- Default alignment for Cylinder is centered in X/Y, `Align.MIN` on Z (grows upward)

## Params Pattern

```python
import json
from pathlib import Path

PARAMS = json.loads(
    Path(__file__).with_name("params.json").read_text(encoding="utf-8")
)
fan_width = float(PARAMS["fan_width"])
```

Load params at module top level. Do not hardcode dimensions in geometry code.
"""


SKILL_VALIDATION_STRATEGY = """# Validation Strategy

## design.json Structure

```json
{
  "schema": "design-spec.v1",
  "model": "bracket",
  "units": "mm",
  "intent": "What this part does",
  "features": [
    {
      "id": "feature_id",
      "intent": "What this feature is for",
      "checks": ["check_id_1", "check_id_2"]
    }
  ],
  "checks": [
    { "id": "check_id_1", "type": "bbox_size", ... }
  ]
}
```

Every feature must reference at least one existing check ID. The validator
enforces feature-to-check coverage automatically.

## Choosing Check Types

### Overall envelope
- `bbox_size` — bounding box dimensions with tolerance
- `volume_range` — volume within min/max range
- `watertight` — manifold mesh (no boundary edges)

### Artifact presence
- `artifact_exists` — file exists at the given path (relative to model dir)

### Holes and circular features
- `outer_diameter_at_z` — section plane intersection, outer diameter estimate
- `inner_diameter_at_z` — section plane intersection, inner diameter estimate
- These use STL triangle-plane intersection, best for axisymmetric geometry

### Tapers, chamfers, and sockets
- `diameter_decreases_along_z` — monotonic diameter change across Z samples
- Combine with `outer_diameter_at_z` at key Z values for both-end verification

### Design intent metadata
- `metadata_equals` — check a path in metadata.json matches expected value
- Use as supplementary evidence, never as the sole check for a feature

### Mesh quality
- `min_triangles` — minimum triangle count (catches degenerate exports)

## Section Checks in Detail

Section checks slice the STL at a given Z height and estimate radial envelope
around a center point. They work best for axisymmetric features (cylinders,
ducts, sockets, tapers).

```json
{
  "id": "socket_od_at_z10",
  "type": "outer_diameter_at_z",
  "z": 10.0,
  "expected": 79.4,
  "tolerance": 0.3,
  "center": [0.0, 0.0]
}
```

For off-axis holes (e.g., bolt holes at corners), section checks centered at
(0,0) will not work. Use `metadata_equals` to record the design intent and add
a comment that a geometry check for that position is not yet available.

## Tolerance Selection

- 0.1-0.2 mm: tight fit, bearing surfaces, critical mating dimensions
- 0.3-0.5 mm: general mechanical, slip fits, clearance holes
- 0.5-1.0 mm: non-critical, cosmetic, large structural parts
- STL mesh resolution affects measurement precision. Typical export tolerance
  is around 0.01 mm but section checks use percentile estimation which adds
  ~0.1 mm uncertainty. Do not set tolerances below 0.1 mm for section checks.

## Feature Coverage Strategy

1. List every user-visible or functional feature in `features`
2. For each feature, pick the most direct check type
3. If no existing check type can verify it, use `metadata_equals` as a
   placeholder and note the limitation
4. Never leave a feature without at least one check reference

## Check Design Anti-Patterns

- Checking only bbox + watertight: these pass even when features are missing
- Using metadata_equals as the sole check for a geometry feature
- Setting tolerance to 0: STL mesh quantization makes exact matches unreliable
- Not checking both ends of a taper or socket
"""


SKILL_COMMON_ERRORS = """# Common Errors and Fixes

## Build Errors

### MissingResult: part.py must define global variable result

The script executed but no `result` variable was found in the global scope.

Fix: ensure the last line of part.py assigns the build123d object:
```python
result = bp.part
```
Do not return it from a function and forget to assign.

### NameError or ImportError

Usually a typo in a build123d API name or a missing import. The full traceback
is in `outputs/build.json` under `stderr`.

Fix: read the stderr field in the build report, fix the name, rerun
`cad validate`.

### build123d topology errors

Messages like "Unable to fuse" or "Null shape" mean the boolean operation
produced invalid geometry.

Common causes:
- Zero-thickness solids (two faces exactly coplanar)
- Subtracting a shape that does not intersect the base solid
- Fillet radius larger than the edge length or adjacent face

Fix: reduce fillet/chamfer size, add a small offset between coplanar faces
(0.01 mm is enough), or change boolean operation order.

## Validation Failures

### bbox_size fails but geometry looks correct

The default Box alignment is center on all axes. If you used Align.MIN on Z
and the bbox center shifted, the size dimensions may still match. If size is
wrong, check your parameter values in params.json and ensure you are reading
the right keys.

### watertight is false

The STL mesh has boundary edges. Common causes:
- Zero-thickness walls in the CAD model
- Boolean subtraction that left an open shell
- Extremely small features below mesh resolution

Fix: increase wall thickness to at least 0.8 mm, check boolean operations for
correctness.

### feature_coverage fails

Every feature in `design.json.features` must list at least one check ID that
exists in `design.json.checks`. Check for typos in check IDs and ensure every
feature has a non-empty `checks` array.

### Section checks return unexpected diameters

- `center` defaults to [0, 0]. If the feature is off-center (e.g., a bolt hole
  at a corner), the section slice will measure the wrong profile.
- STL triangle density at the section plane affects precision. If the mesh is
  coarse, increase tolerance.
- `diameter_outer_estimate` uses the 98th percentile radius, not the max. This
  filters outlier artifacts but may slightly underreport the true outer
  diameter. Adjust tolerance accordingly (typically 0.2-0.3 mm is safe).

## Modeling Pitfalls

### Chamfer/fillet hidden by overlapping geometry

A chamfer coded correctly can be visually hidden if a later operation adds a
cylinder or box that overlaps the chamfered region. The geometry is technically
correct but the chamfer serves no purpose.

Prevention: use `outer_diameter_at_z` or `diameter_decreases_along_z` checks
at the chamfer location to verify the surface actually changes.

### Wrong Align causing off-center parts

```python
# This box is centered at origin
Box(40, 30, 20)

# This box starts at Z=0 and extends upward
Box(40, 30, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))
```

Be explicit about alignment. If a flange should sit on top of another part,
use Align.MIN on Z for the base and Align.MIN for the added part, then offset
with `with Locations(...)`.

### Hole depth does not go all the way through

`Hole(radius)` without depth goes through the full part thickness. Specifying
`depth=X` makes it X mm deep from the current workplane. If the workplane is
not where you think it is, the hole may stop short.

Fix: use `Hole(radius)` without depth for through-holes. For blind holes, be
explicit about the workplane location.
"""


REFERENCE_NOTES = """# References

Put images, sketches, scan files, and user notes for this CAD project here.
"""


def model_readme(name: str) -> str:
    return f"""# {name}

AgentCAD model folder.

Edit:

- `design.json` for design intent and validation checks
- `params.json` for tunable dimensions
- `part.py` for build123d geometry

Generated artifacts for this model are written to this folder's `outputs/`
directory. The project root does not have a shared outputs directory in V0.
"""


def model_params() -> str:
    return json.dumps(
        {
            "length": 40.0,
            "width": 30.0,
            "height": 20.0,
        },
        indent=2,
    ) + "\n"


def model_design(name: str) -> str:
    return json.dumps(
        {
            "schema": "design-spec.v1",
            "model": name,
            "units": "mm",
            "intent": "Default rectangular sample block.",
            "features": [
                {
                    "id": "base_block",
                    "intent": "Rectangular solid block with parameter-driven envelope.",
                    "checks": ["bbox_size", "watertight"],
                }
            ],
            "checks": [
                {"id": "bbox_size", "type": "bbox_size", "expected": [40.0, 30.0, 20.0], "tolerance": 0.2},
                {"id": "watertight", "type": "watertight", "expected": True},
                {"type": "artifact_exists", "path": f"outputs/{name}.step"},
                {"type": "artifact_exists", "path": f"outputs/{name}.stl"},
            ],
        },
        indent=2,
    ) + "\n"


def model_part() -> str:
    return '''"""Default AgentCAD build123d model.

Tunable values live in params.json. The final geometry must be assigned to
global variable `result`.
"""
import json
from pathlib import Path

from build123d import *

PARAMS = json.loads((Path(__file__).with_name("params.json")).read_text(encoding="utf-8"))

length = float(PARAMS["length"])
width = float(PARAMS["width"])
height = float(PARAMS["height"])


def build():
    with BuildPart() as bp:
        add(Box(length, width, height))
    return bp.part


result = build()
metadata = {
    "schema": "agentcad.part.metadata.v1",
    "units": "mm",
    "anchors": {
        "origin": [0, 0, 0],
        "x_min": [-length / 2, 0, 0],
        "x_max": [length / 2, 0, 0],
    },
}
'''
