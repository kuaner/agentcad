# duct_socket(outer_diameter, inner_diameter, length)

Cylindrical duct socket with wall thickness and optional lead-in taper.
Returns a positive solid (outer cylinder with inner bore already subtracted).

```python
from agentcad.features import duct_socket

socket = duct_socket(80, 79.4, 28, lead_in=2, builder=b, feature_id="duct")
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `outer_diameter` | float | required | Outer wall diameter (mm) |
| `inner_diameter` | float | required | Bore diameter (mm) |
| `length` | float | required | Socket length in Z (mm) |
| `lead_in` | float | 0 | Diameter reduction at open end (mm) |
| `center` | (float, float) | (0,0) | XY center |
| `base_z` | float | 0 | Z base position |
| `builder` | ContractBuilder | None | Register checks |
| `feature_id` | str | "duct_socket" | ID prefix |

## Auto-generated Checks

| Check ID | Type | When |
|---|---|---|
| `{id}_id` | `inner_diameter_at_z` | always |
| `{id}_taper` | `diameter_decreases_along_z` | `lead_in > 0` |

The taper check verifies the socket narrows monotonically from base to tip,
catching reversed or missing lead-in chamfers.
