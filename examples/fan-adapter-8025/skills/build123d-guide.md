# build123d Modeling Guide

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
