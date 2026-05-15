# rounding_mask(length, edge, size)

Edge fillet/roundover mask. Subtract from your part to create rounded edges.

```python
from agentcad.features import rounding_mask

rm = rounding_mask(80, edge="z", size=2, builder=b, feature_id="round_edge")
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `length` | float | required | Fillet length along the edge axis (mm) |
| `edge` | str | "z" | Axis the fillet runs along: "x", "y", or "z" |
| `size` | float | 1.0 | Fillet radius — quarter-circle arc radius (mm) |
| `builder` | ContractBuilder | None | Register checks (none auto-generated) |
| `feature_id` | str | "rounding" | Feature/check ID prefix |

## Auto-generated Checks

None (cosmetic feature, like chamfer_mask).

## Usage

```python
from build123d import BuildPart, add, subtract
from agentcad.features import ContractBuilder, plate, rounding_mask

b = ContractBuilder()
with BuildPart() as bp:
    plank = plate(60, 40, 5, builder=b, feature_id="base")
    add(plank)

    # Round the top Z-edges
    rm = rounding_mask(60, edge="z", size=1.5, builder=b, feature_id="round_edge")
    subtract(rm)

result = bp.part
```

The rounding mask has a quarter-circle profile (arc from one face to the other). It has more volume than a chamfer_mask of the same size because the arc fills more space than the triangle.