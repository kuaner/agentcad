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
"""


SKILL_BUILD123D_GUIDE = """# build123d Modeling Guide

Reference for writing `part.py` files. Uses the Builder API (context managers).
`from build123d import *` imports everything needed.

## Builder Context Managers

All geometry is created inside builders. Builders track all objects created within
them and allow query/selection of topology.

### BuildPart — 3D solid modeling

```python
with BuildPart() as bp:
    add(Box(30, 20, 10))                # base solid
    fillet(bp.edges()[-4:], radius=2)    # modify edges
    with Locations((0, 0, 10)):          # position context
        Cylinder(radius=5, height=8)     # add feature
result = bp.part                         # extract the Shape
```

Key methods on `bp`:
- `bp.part` — the final Compound/Shape
- `bp.solids()` — all solid bodies
- `bp.faces()` — all faces
- `bp.edges()` — all edges
- `bp.vertices()` — all vertices

### BuildSketch — 2D profiles

```python
with BuildSketch() as sk:
    Rectangle(30, 20)
    with Locations((0, 0)):
        Circle(radius=5, mode=Mode.SUBTRACT)
result_sketch = sk.sketch
```

BuildSketch operates on the default Plane.XY (Z=0) unless a workplane is
specified. Sketches are extruded via `extrude()` inside BuildPart, or used
with `add(Sketch)`.

### BuildLine — 1D wire paths

```python
with BuildLine() as ln:
    l1 = Line((0, 0), (10, 0))
    l2 = Line((10, 0), (10, 5))
    l3 = Line((10, 5), (0, 0))
result_line = ln.line
```

Used for sweep paths, lofts, and complex profiles.

## Key Enums

### Align — positioning on each axis

```
Align.MIN    = toward negative end (-X, -Y, or -Z)
Align.CENTER = centered (default for most objects)
Align.MAX    = toward positive end (+X, +Y, or +Z)
```

All 3D primitives accept `align=(x, y, z)` tuple. Example:
```python
# Box sitting on Z=0 plane, centered in X/Y
Box(30, 20, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))

# Cylinder growing upward from origin
Cylinder(radius=5, height=20, align=(Align.CENTER, Align.CENTER, Align.MIN))
```

Defaults: Box = CENTER on all axes. Cylinder = CENTER X/Y, MIN Z.

### Mode — how objects combine

```
Mode.ADD       = boolean union (default)
Mode.SUBTRACT  = boolean cut
Mode.INTERSECT = boolean intersection
Mode.REPLACE   = replace the builder's shape entirely
Mode.PRIVATE   = create but don't combine with the builder
```

```python
# Subtract a circle from a rectangle (cut a hole)
with BuildSketch() as sk:
    Rectangle(30, 20)
    Circle(radius=5, mode=Mode.SUBTRACT)
```

### Select — which objects an operation targets

```
Select.ALL   = operate on all topology in builder
Select.LAST  = operate on most recently created objects
Select.NEW   = operate on objects not yet consumed (default for many ops)
```

Most operations default to Select.NEW. `fillet` and `chamfer` accept an
explicit list of edges/faces.

### GeomType — edge/face geometry classification

```
GeomType.LINE    = straight line edge
GeomType.CIRCLE  = circular arc or full circle
GeomType.ELLIPSE = elliptical arc
GeomType.BSPLINE = spline curve
GeomType.PLANE   = flat face
GeomType.CYLINDER = cylindrical face
GeomType.CONE    = conical face
GeomType.SPHERE  = spherical face
```

Used with `filter_by(GeomType.LINE)` to narrow edge/face selections.

### SortBy — alternative sort criteria

```
SortBy.RADIUS  = sort circles/arcs by radius
SortBy.LENGTH  = sort edges by length
SortBy.AREA    = sort faces by area
SortBy.DISTANCE = sort by distance from origin
```

## 3D Primitives

| Object | Key parameters |
|--------|---------------|
| `Box(length, width, height, align)` | Rectangular solid |
| `Cylinder(radius, height, align, rotation)` | Cylindrical solid |
| `Cone(bottom_radius, top_radius, height, align)` | Truncated cone. `top_radius=0` for full cone |
| `Sphere(radius)` | Spherical solid |
| `Torus(outer_ring_radius, tube_radius)` | Toroidal solid |
| `Wedge(dx, dy, dz, xmin, zmin, xmax, zmax)` | Wedge with optional angle cuts |

```python
# Box aligned to sit on Z=0
add(Box(40, 30, 10, align=(Align.CENTER, Align.CENTER, Align.MIN)))

# Cone (chamfer-like taper)
add(Cone(bottom_radius=10, top_radius=8, height=5))

# Cylinder with specific rotation
add(Cylinder(radius=5, height=20, rotation=(90, 0, 0)))  # rotated to lie along X
```

## 2D Primitives (for BuildSketch)

| Object | Key parameters |
|--------|---------------|
| `Rectangle(width, height, align)` | Aligned rectangle |
| `Circle(radius)` | Circle at origin |
| `Ellipse(major_radius, minor_radius)` | Ellipse |
| `Polygon(points)` | Polygon from point list |
| `Polygon(pts, side_count)` | Regular polygon |
| `Trapezoid(width, height, left_side_angle)` | Trapezoid |
| `Slot(width, height)` | Rounded-end slot |
| `Triangle(a, b, c)` | Triangle from side lengths |

All 2D objects support `mode=Mode.SUBTRACT` to cut from the sketch.

## 1D Primitives (for BuildLine)

| Object | Key parameters |
|--------|---------------|
| `Line(start, end)` | Straight line between two points |
| `Arc(start, middle, end)` | Circular arc through three points |
| `RadiusArc(start, end, radius)` | Arc defined by radius |
| `TangentArc(start, end, tangent)` | Arc tangent to direction at start |
| `Spline(points)` | BSpline through points |
| `PolarLine(start, length, angle)` | Line at angle from start |
| `Helix(pitch, height, radius)` | Helical curve (for threads) |

## Operations

### 3D Operations (inside BuildPart)

| Operation | Parameters | Description |
|-----------|-----------|-------------|
| `fillet(edges, radius)` | list of edges, radius | Round edges |
| `chamfer(edges, length)` | list of edges, length | Bevel edges |
| `extrude(amount)` | distance (mm) | Extrude pending sketch into solid |
| `revolve(amount)` | revolution angle (default 360) | Revolve pending sketch |
| `loft()` | — | Loft between pending sketches |
| `sweep(path)` | path (wire/line) | Sweep pending sketch along path |
| `mirror(about)` | Plane or Axis | Mirror about plane/axis |
| `offset(amount)` | distance (positive=outward) | Offset shell/faces |
| `split(keep)` | Plane or keep=Keep.TOP/BOTTOM | Split and keep half |
| `scale(factor)` | scale factor | Scale uniformly |
| `thicken(amount)` | thickness | Thicken a face into solid |

### Hole Operations

| Operation | Parameters | Description |
|-----------|-----------|-------------|
| `Hole(radius, depth=None)` | radius, optional depth | Simple hole (through if no depth) |
| `CounterBoreHole(radius, depth, counter_bore_radius, counter_bore_depth)` | — | Socket-head screw hole |
| `CounterSinkHole(radius, counter_sink_radius, counter_sink_angle=82, depth=None)` | — | Flat-head screw hole |

Holes operate on the current workplane. Without `depth`, `Hole` goes through
the full part thickness.

### 2D Operations (inside BuildSketch)

| Operation | Description |
|-----------|-------------|
| `fillet(edges, radius)` | Round 2D edges |
| `chamfer(edges, length)` | Bevel 2D edges |
| `offset(amount)` | Offset sketch outline |
| `mirror(about)` | Mirror about axis |
| `trim(edge)` | Trim at intersection |

## Positioning: Location Contexts

Location contexts set the workplane for everything created inside them. They
are stacked: nesting adds transforms.

### Locations — explicit positions

```python
# Single position
with Locations((10, 5, 0)):
    Hole(radius=2)

# Multiple positions (creates feature at each)
with Locations((10, 5, 0), (-10, 5, 0)):
    Hole(radius=2)

# Using a face to set workplane
with Locations(bp.faces().sort_by(Axis.Z)[-1]):
    Hole(radius=2)
```

### GridLocations — rectangular array

```python
# 2x3 grid, 20mm X spacing, 15mm Y spacing
with GridLocations(20, 15, 2, 3):
    Hole(radius=2)
```

### PolarLocations — circular array

```python
# 6 holes on a 30mm bolt circle
with PolarLocations(30, 6):
    Hole(radius=2)

# Start angle offset, angular range
with PolarLocations(30, 4, start_angle=45, angular_range=180):
    Hole(radius=2)
```

### HexLocations — hex grid pattern

```python
# Hex grid for weight reduction pockets
with HexLocations(8, 3, 4, align=(Align.CENTER, Align.MIN)):
    Circle(radius=3, mode=Mode.SUBTRACT)
```

## Location Arithmetic

`Location` objects can be composed with `*` and created from tuples or
named args:

```python
# Create and combine locations
loc = Location((10, 0, 0)) * Location((0, 5, 0))  # combined offset

# Rotation
rot_loc = Location((0, 0, 0), (90, 0, 0))  # 90 deg around X

# Move an existing object
moved_box = Box(10, 10, 5).moved(Location((0, 0, 20)))
```

`.moved()` returns a new object at the given location. It does not mutate
the original.

## Selecting Topology

Builders expose topology selectors: `bp.solids()`, `bp.faces()`, `bp.edges()`,
`bp.vertices()`. These return `ShapeList` objects with powerful filtering.

### ShapeList Methods

```python
edges = bp.edges()

# Filter by axis alignment (edges parallel to Z)
z_edges = edges.filter_by(Axis.Z)

# Filter by geometry type
lines = edges.filter_by(GeomType.LINE)
circles = edges.filter_by(GeomType.CIRCLE)

# Sort along axis (ascending)
sorted_by_z = edges.sort_by(Axis.Z)
highest = sorted_by_z[-1]          # top edge
lowest_four = sorted_by_z[:4]      # bottom 4 edges

# Sort by alternative criteria
by_radius = edges.sort_by(SortBy.RADIUS)
largest_circle = by_radius[-1]

# Group by axis (returns list of ShapeLists)
groups = edges.group_by(Axis.Z)
# groups[0] = edges with lowest Z, groups[-1] = highest Z

# Position-based filtering
specific = [e for e in edges
            if abs(e.center().Z - 5.0) < 0.1]
```

### ShapeList Operators

```python
# Comparison: select elements above/below a position along axis
high = edges > Axis.Z      # edges with center.Z > 0
low = edges < Axis.Z       # edges with center.Z < 0

# Shift: select neighbors by index offset
last4 = edges >> 4         # last 4 edges (from sorted order)
first4 = edges << 4        # first 4 edges

# Union: combine two ShapeLists
combined = z_edges | circle_edges

# Index: access by position
first = edges[0]
last = edges[-1]
```

### Selector Strategy for Fillet/Chamfer

```python
# 1. Get all edges from the builder
edges = bp.edges()

# 2. Filter by geometry type
line_edges = edges.filter_by(GeomType.LINE)

# 3. Filter by axis (edges parallel to Z)
vertical = line_edges.filter_by(Axis.Z)

# 4. Sort and slice
sorted_v = vertical.sort_by(Axis.Z)
top_4 = sorted_v[-4:]      # 4 highest vertical edges
bottom_4 = sorted_v[:4]    # 4 lowest vertical edges

fillet(top_4, radius=3)
chamfer(bottom_4, length=1)
```

For edges at a specific position (e.g., junction between two parts):
```python
# Filter by center position with tolerance
junction = [e for e in bp.edges().filter_by(GeomType.LINE).filter_by(Axis.X)
            if abs(e.center().Z - junction_z) < 0.1
            and abs(e.center().Y - junction_y) < 0.1]
if junction:
    fillet(junction, radius=r)
```

## Workplanes and Planes

`BuildSketch` and hole operations use the current workplane. The default is
Plane.XY (the XY plane at Z=0).

```python
# Sketch on XZ plane (e.g., for a side profile)
with BuildSketch(Plane.XZ) as sk:
    Rectangle(20, 10)
    extrude(amount=5)  # extrude along Y axis

# Sketch on a face
with BuildSketch(bp.faces().sort_by(Axis.Z)[-1]) as sk:
    Circle(radius=5)
    extrude(amount=3)  # boss growing upward from top face

# Custom plane offset from XY
custom = Plane(origin=(0, 0, 10), x_dir=(1, 0, 0), z_dir=(0, 0, 1))
```

Key planes: `Plane.XY`, `Plane.XZ`, `Plane.YZ`, `Plane(origin, x_dir, z_dir)`.

## Sketch-to-Solid Workflow

### Extrude

```python
with BuildPart() as bp:
    with BuildSketch():
        Rectangle(30, 20)
        Circle(radius=5, mode=Mode.SUBTRACT)  # hole in sketch
    extrude(amount=10)  # 10mm thick, Z direction by default
result = bp.part
```

### Revolve

```python
with BuildPart() as bp:
    with BuildSketch(Plane.XZ) as sk:
        # Profile on XZ plane, will revolve around Z axis
        with Locations((15, 0)):
            Rectangle(5, 10)
    revolve(amount=360)  # full revolution
result = bp.part
```

### Sweep

```python
with BuildPart() as bp:
    with BuildSketch():
        Circle(radius=3)
    with BuildLine() as ln:
        # Sweep path
        Spline([(0,0,0), (10,0,5), (20,0,0)])
    sweep(path=ln.line)
result = bp.part
```

### Loft

```python
with BuildPart() as bp:
    # Bottom profile
    with BuildSketch(Plane.XY):
        Rectangle(20, 20)
    # Top profile (offset plane)
    with BuildSketch(Plane.XY.offset(15)):
        Circle(radius=8)
    loft()
result = bp.part
```

## Complete Patterns

### L-Bracket

```python
with BuildPart() as bp:
    # Base plate on Z=0
    add(Box(base_length, base_width, base_thickness,
            align=(Align.CENTER, Align.CENTER, Align.MIN)))

    # Vertical web at back edge, rising from top of base
    add(Box(base_length, web_thickness, web_height,
            align=(Align.CENTER, Align.MAX, Align.MIN))
        .moved(Location((0, base_width / 2, base_thickness))))

    # Fillet interior junction
    junction = [e for e in bp.edges().filter_by(GeomType.LINE).filter_by(Axis.X)
                if abs(e.center().Z - base_thickness) < 0.1
                and abs(e.center().Y - (base_width/2 - web_thickness/2)) < 0.1]
    if junction:
        fillet(junction, radius=fillet_radius)

    # Base mounting holes (from top face down)
    with Locations((-hole_spacing/2, -margin, base_thickness)):
        CounterBoreHole(radius=r, depth=d, counter_bore_radius=cr, counter_bore_depth=cd)
    with Locations((hole_spacing/2, -margin, base_thickness)):
        CounterBoreHole(radius=r, depth=d, counter_bore_radius=cr, counter_bore_depth=cd)

    # Web mounting holes (from outer face inward)
    for z in (base_thickness + margin_z, base_thickness + margin_z + spacing_z):
        with Locations((0, base_width, z)):
            CounterBoreHole(radius=r, depth=d, counter_bore_radius=cr, counter_bore_depth=cd)

result = bp.part
```

### Tube / Pipe

```python
with BuildPart() as bp:
    add(Cylinder(radius=outer_r, height=length,
                 align=(Align.CENTER, Align.CENTER, Align.MIN)))
    with Locations((0, 0, length)):  # workplane at top
        Hole(radius=inner_r)         # through-hole
result = bp.part
```

### Flange with Bolt Pattern

```python
with BuildPart() as bp:
    add(Box(flange_w, flange_w, flange_h,
            align=(Align.CENTER, Align.CENTER, Align.MIN)))
    # Center bore
    with Locations((0, 0)):
        Hole(radius=bore_r)
    # Corner bolt holes
    with GridLocations(spacing, spacing, 2, 2):
        Hole(radius=screw_r)
result = bp.part
```

### Swept Profile (Duct)

```python
with BuildPart() as bp:
    with BuildSketch():
        Rectangle(width, height)
    with BuildLine() as path:
        Line((0, 0), (0, duct_length))
    sweep(path=path.line)
result = bp.part
```

## Operation Order

The order of operations inside BuildPart matters critically:

1. **Add base solid** — `add(Box(...))` or `add(Cylinder(...))`
2. **Fillet/chamfer structural edges** — before boolean cuts that change topology
3. **Subtract features** — holes, pockets, CounterBoreHole
4. **Add bosses** — cylinders, extruded sketches

```python
# WRONG: fillet after hole picks wrong edges
with BuildPart() as bp:
    add(Box(30, 30, 10))
    Hole(radius=5)           # changes edge topology
    fillet(bp.edges()[-4:], radius=2)  # -4 picks wrong edges now

# RIGHT: fillet before subtracting
with BuildPart() as bp:
    add(Box(30, 30, 10))
    fillet(bp.edges().filter_by(Axis.Z)[-4:], radius=2)
    Hole(radius=5)
```

## Coordinate Convention

- +X right, +Y back, +Z up
- Origin (0,0,0) is center of the default workspace
- `Align.MIN` = negative side, `Align.CENTER` = centered, `Align.MAX` = positive side

## Params Pattern

```python
import json
from pathlib import Path

PARAMS = json.loads(
    Path(__file__).with_name("params.json").read_text(encoding="utf-8")
)
length = float(PARAMS["length"])
width = float(PARAMS["width"])
height = float(PARAMS["height"])
```

Load params at module top level. Do not hardcode dimensions in geometry code.

## Common Pitfalls

### 1. Fillet radius too large
If the radius exceeds the edge length or adjacent face width, the boolean fails
with a topology error. Reduce radius.

### 2. Zero-thickness geometry
Two faces exactly coplanar causes boolean failures. Add a 0.01mm gap if needed.

### 3. Workplane confusion
BuildSketch defaults to Plane.XY (Z=0). Holes go in the -Z direction from the
current workplane. If a hole doesn't go through, check the workplane location.

### 4. Nested builders don't inherit workplanes
```python
# BuildSketch inside BuildPart does NOT inherit BuildPart's workplane
with BuildPart() as bp:
    add(Box(50, 50, 10, align=(Align.CENTER, Align.CENTER, Align.MIN)))
    with BuildSketch():  # still Plane.XY, NOT top of box
        Rectangle(5, 5)
    extrude(amount=3)    # extrudes from Z=0 upward
```

To sketch on top of the box:
```python
with BuildSketch(bp.faces().sort_by(Axis.Z)[-1]):
    Rectangle(5, 5)
extrude(amount=3)
```

### 5. Self-intersection
Objects that intersect themselves (e.g., a wall with zero thickness where two
sides meet) create invalid BREP. Ensure all solid walls have material thickness.

### 6. ShapeList slicing vs single edge
`edges.sort_by(Axis.Z)[-1]` returns a single Edge. `edges.sort_by(Axis.Z)[-2:]`
returns a ShapeList. Both work with `fillet()`. But `[-0:]` is wrong — use `[-1]`.

### 7. Cylinder rotation
`Cylinder` grows along its local Z axis. To orient it along X or Y, use
`rotation=(90, 0, 0)` to rotate around X, or `rotation=(0, 90, 0)` to rotate
around Y.

### 8. Using .moved() correctly
`.moved(Location(...))` returns a NEW object. The original is unchanged.
```python
web = Box(L, W, H, align=...).moved(Location((0, offset, Z)))
add(web)  # add the moved copy
```
"""


SKILL_VALIDATION_STRATEGY = """# Validation Strategy & Troubleshooting

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

## Build Error Troubleshooting

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

## Validation Failure Troubleshooting

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
