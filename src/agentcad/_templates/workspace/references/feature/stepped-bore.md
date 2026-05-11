# stepped_bore(spec, bore_kind)

Through-hole with counterbore or countersink for screw head recess.
Returns a **SteppedBore** object — call ``cut()`` inside a BuildPart context to subtract.

```python
from agentcad.features import SteppedBore

bore = SteppedBore("M3_cap", bore_kind="counterbore", through_depth=8, builder=b)
bore.cut()  # inside a with BuildPart() block
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `spec` | str or Screw | required | Screw spec |
| `center` | (float, float) | (0,0) | XY center |
| `through_depth` | float | 10 | Total through-hole depth |
| `bore_kind` | str | "counterbore" | `"counterbore"`, `"countersink"`, `"plain"` |
| `fit` | str | "normal" | `"tight"`, `"normal"`, `"loose"` |
| `builder` | ContractBuilder | None | Register checks |
| `feature_id` | str | "stepped_bore" | ID prefix |

## Bore Kinds

| Kind | Description |
|---|---|
| `counterbore` | Flat-bottom cylindrical recess for socket/cap head |
| `countersink` | Conical recess (90° included angle) for flat/countersunk head |
| `plain` | Through-hole only, no head recess |

## Auto-generated Checks

| Check ID | Type | When |
|---|---|---|
| `{id}_through` | `inner_diameter_at_z` | always |
| `{id}_recess` | `inner_diameter_at_z` | `bore_kind="counterbore"` |

Counterbore and recess dimensions come from the screw spec's real ISO head
dimensions (e.g. M3_cap head_diameter=5.5, head_height=3.0).