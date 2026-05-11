# chamfer_mask(length, edge="z", size=1.0)

Edge chamfer wedge. Returns a positive solid — subtract it from your part to create a chamfer along an edge.

```python
from agentcad.features import chamfer_mask

cm = chamfer_mask(50, edge="z", size=2, builder=b, feature_id="top_chamfer")
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `length` | float | required | Chamfer length along the edge axis (mm) |
| `edge` | str | "z" | Which axis the chamfer runs along: "x", "y", or "z" |
| `size` | float | 1.0 | Distance from corner to base along each adjacent face (mm) |
| `builder` | ContractBuilder | None | Register feature (no auto-checks) |
| `feature_id` | str | "chamfer" | Feature ID prefix |

## Auto-generated Checks

No automatic checks. The chamfer is a cosmetic feature — register it manually if you need a check.

## Usage

```python
from build123d import BuildPart, add, Location, Mode
from agentcad.features import ContractBuilder, chamfer_mask

b = ContractBuilder()
with BuildPart() as bp:
    # ... build your part ...
    cm = chamfer_mask(70, edge="z", size=1.5)
    add(cm.moved(Location((0, 0, 10))), mode=Mode.SUBTRACT)
result = bp.part
```

The chamfer wedge is a right triangle extruded along the specified axis. Position it at the edge you want to chamfer and subtract it.