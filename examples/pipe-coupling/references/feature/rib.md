# rib(length, height, thickness)

Reinforcing rib (thin wall). Returns a positive solid.

```python
from agentcad.features import rib

wall = rib(30, 10, 3, origin=(0, 10, 5), direction="x", builder=b)
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `length` | float | required | Length along direction axis (mm) |
| `height` | float | required | Height in Z (mm) |
| `thickness` | float | required | Rib thickness (mm) |
| `origin` | (float,float,float) | (0,0,0) | Origin point |
| `direction` | str | "x" | Length axis: `"x"` or `"y"` |
| `builder` | ContractBuilder | None | Register checks |
| `feature_id` | str | "rib" | ID prefix |

## Auto-generated Checks

| Check ID | Type |
|---|---|
| `{id}_thickness` | `min_wall_thickness` |

The check verifies the rib maintains its declared thickness at the mid-Z
section. For FDM printing, `thickness >= 1.5mm` (2 perimeters × 0.45mm nozzle +
infill) is recommended.
