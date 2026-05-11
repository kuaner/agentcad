# boss(diameter, height)

Raised cylindrical boss, optionally with a through-hole. Returns a positive solid.

```python
from agentcad.features import boss

pillar = boss(10, 8, inner_diameter=4, builder=b, feature_id="center_boss")
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `diameter` | float | required | Outer diameter (mm) |
| `height` | float | required | Boss height (mm) |
| `center` | (float, float) | (0,0) | XY center |
| `base_z` | float | 0 | Z base position |
| `inner_diameter` | float | 0 | Through-hole diameter (0 = solid boss) |
| `builder` | ContractBuilder | None | Register checks |
| `feature_id` | str | "boss" | ID prefix |

## Auto-generated Checks

| Check ID | Type | When |
|---|---|---|
| `{id}_hole` | `inner_diameter_at_z` | `inner_diameter > 0` |

No check is generated for a solid boss (no hole). Add a manual
`min_wall_thickness` or `feature_position` check if the boss-to-parent
connection needs verification.
