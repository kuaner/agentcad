# build123d Modeling Guide

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

### 9. ⚠️ CRITICAL: Locations does NOT shift BuildSketch plane in Z

`Locations((x, y, z))` works perfectly for **3D primitives** (Box, Cylinder, Cone)
but does **NOT** relocate the plane of `BuildSketch`. The sketch always materialises
on the plane you pass to `BuildSketch(...)`, regardless of any enclosing `Locations`.

```python
# WRONG — inner cavity will start at Z=0, not at Z=wall_back
with Locations((0, 0, wall_back)):
    with BuildSketch(Plane.XY):       # still Z=0 globally
        RectangleRounded(w, h, r)
    extrude(amount=depth, mode=Mode.SUBTRACT)

# CORRECT — use an explicit Plane with the desired origin
with BuildSketch(Plane(origin=(0, 0, wall_back))):
    RectangleRounded(w, h, r)
extrude(amount=depth, mode=Mode.SUBTRACT)

# ALSO CORRECT — for off-axis features combine X/Y/Z in the origin
cam_cx, cam_cy = -10.3, 53.3
with BuildSketch(Plane(origin=(cam_cx, cam_cy, -0.1))):
    RectangleRounded(cam_w, cam_h, cam_r)
extrude(amount=wall_back + 0.2, mode=Mode.SUBTRACT)
```

**Rule of thumb:**
- `Locations` → use it only with 3D primitives (Box, Cylinder, Cone, Sphere).
- `BuildSketch` → always pass the plane explicitly: `Plane(origin=(x, y, z))`.

Symptom of the bug: a feature that should start at Z>0 (e.g., an inner cavity)
instead starts at Z=0, obliterating the back wall. Or a cutout that should remove
material from a back panel removes nothing because the back panel never existed.

Diagnostic: intersect the part with a probe `Box(w, h, ε)` at the expected Z
height and check the resulting volume. Zero volume means no material at that Z.

### 1. Fillet radius too large
If the radius exceeds the edge length or adjacent face width, the boolean fails
with a topology error. Reduce radius.

### 2. Zero-thickness geometry
Two faces exactly coplanar causes boolean failures. Add a 0.01mm gap if needed.

### 3. Workplane confusion
BuildSketch defaults to Plane.XY (Z=0). Holes go in the -Z direction from the
current workplane. If a hole doesn't go through, check the workplane location.
Use `Plane(origin=(x, y, z))` to place a sketch at an arbitrary position in space
(see pitfall #9 above — never rely on Locations for this).

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
