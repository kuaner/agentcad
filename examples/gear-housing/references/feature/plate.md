# plate(width, depth, thickness)

Flat rectangular plate with optional edge fillets. Returns a positive solid.

```python
from agentcad.features import plate

plank = plate(100, 50, 5, fillet_r=2, builder=b, feature_id="base")
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `width` | float | required | X dimension (mm) |
| `depth` | float | required | Y dimension (mm) |
| `thickness` | float | required | Z dimension (mm) |
| `fillet_r` | float | 0 | Edge fillet radius (0 = sharp edges) |
| `builder` | ContractBuilder | None | Register checks |
| `feature_id` | str | "plate" | Feature/check ID prefix |
| `bbox_tolerance` | float | 0.5 | Tolerance for bbox check |

## Auto-generated Checks

| Check ID | Type | When |
|---|---|---|
| `{id}_bbox` | `bbox_size` | always |
| `{id}_watertight` | `watertight` | fillet_r > 0 |

## Usage

```python
from build123d import BuildPart, add
from agentcad.features import ContractBuilder, plate

b = ContractBuilder()
with BuildPart() as bp:
    body = plate(86, 86, 5, builder=b, feature_id="flange")
    add(body)
result = bp.part
```
