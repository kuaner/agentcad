# sparse_wall(size, strut, spacing)

Lightweight rectangular infill wall. Grid of vertical and horizontal struts inside a rectangular frame, leaving open cells between.

```python
from agentcad.features import sparse_wall

wall = sparse_wall((50, 30), strut=2, spacing=10, builder=b, feature_id="wall")
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `size` | tuple | — | (width, depth) or (width, depth, height). Height defaults to strut width |
| `strut` | float | — | Grid wall thickness in mm |
| `spacing` | float | — | Center-to-center distance between struts |
| `center` | tuple[float, float] | (0, 0) | XY center position |
| `base_z` | float | 0 | Z position of the base |
| `builder` | ContractBuilder | None | Register checks |
| `feature_id` | str | "sparse_wall" | Feature/check ID prefix |

## Auto-generated Checks

| Check ID | Type | When |
|---|---|---|
| `{id}_bbox` | `bbox_size` | always (overall dimensions) |
| `{id}_volume` | `volume_range` | always (10-70% of solid wall volume) |

## Usage

```python
from build123d import BuildPart, add
from agentcad.features import ContractBuilder, sparse_wall

b = ContractBuilder(intent="lightweight panel")
with BuildPart() as bp:
    wall = sparse_wall((80, 60, 6), strut=2, spacing=15, builder=b, feature_id="panel")
    add(wall)
result = bp.part
```

For honeycomb infill (hex cells), use `hex_panel` instead.