# slot(width, depth, height)

Rectangular channel. Returns a **negative** solid — subtract from parent.

```python
from agentcad.features import slot

groove = slot(5, 3, 40, direction="x", builder=b, feature_id="cable_slot")
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `width` | float | required | Slot width across opening (mm) |
| `depth` | float | required | Slot depth / cut depth (mm) |
| `height` | float | required | Slot length along direction (mm) |
| `center` | (float, float) | (0,0) | XY center |
| `base_z` | float | 0 | Z base position |
| `direction` | str | "x" | Length axis: `"x"` or `"y"` |
| `builder` | ContractBuilder | None | Register checks |
| `feature_id` | str | "slot" | ID prefix |

## Auto-generated Checks

| Check ID | Type |
|---|---|
| `{id}_section` | `section_bbox_at_z` (expected="void") |

The section check verifies the slot is empty (void) at mid-depth, catching
cases where the subtraction failed or the slot was filled by a later operation.
