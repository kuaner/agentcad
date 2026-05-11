# threaded_nut(spec)

Hex nut with internal sinusoidal thread. Complement to `threaded_rod` — the nut has an internal helical thread profile for assembly visualization.

```python
from agentcad.features import threaded_nut

nut = threaded_nut("M3", builder=b, feature_id="m3_tnut")
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `spec` | str or Nut | "M3" | Nut specification ("M3", "M4", "M5", etc.) |
| `center` | tuple[float, float] | (0, 0) | XY center position |
| `base_z` | float | 0 | Z position of the base |
| `builder` | ContractBuilder | None | Register checks |
| `feature_id` | str | "threaded_nut" | Feature/check ID prefix |

## Auto-generated Checks

| Check ID | Type | When |
|---|---|---|
| `{id}_bore` | `inner_diameter_at_z` | always (thread bore diameter) |

## Usage

```python
from build123d import BuildPart, add
from agentcad.features import ContractBuilder, threaded_rod, threaded_nut

b = ContractBuilder(intent="threaded pair")
rod = threaded_rod("M3", length=20, builder=b, feature_id="m3_rod")
nut = threaded_nut("M3", builder=b, feature_id="m3_nut")
```

Thread pitch comes from the ISO coarse pitch table. Hex dimensions come from the hardware database (`agentcad.hardware.nuts`). For a plain hex nut without threads, use `nut_body` instead.