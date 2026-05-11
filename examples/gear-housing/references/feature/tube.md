# tube(outer_diameter, inner_diameter, height)

Hollow cylinder (sleeve, bushing, spacer). Returns a positive solid.

```python
from agentcad.features import tube

spacer = tube(outer_diameter=20, inner_diameter=14, height=15, builder=b, feature_id="spacer")
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `outer_diameter` | float | required | Outer diameter (mm) |
| `inner_diameter` | float | required | Inner diameter (mm) |
| `height` | float | required | Tube height along Z (mm) |
| `center` | tuple[float, float] | (0, 0) | XY center position |
| `base_z` | float | 0 | Z position of the tube base |
| `fillet_r` | float | 0 | Edge fillet radius (0 = sharp edges) |
| `builder` | ContractBuilder | None | Register checks |
| `feature_id` | str | "tube" | Feature/check ID prefix |

## Auto-generated Checks

| Check ID | Type | When |
|---|---|---|
| `{id}_outer` | `outer_diameter_at_z` | always |
| `{id}_inner` | `inner_diameter_at_z` | always |

## Usage

```python
from build123d import BuildPart, add
from agentcad.features import ContractBuilder, tube

b = ContractBuilder()
with BuildPart() as bp:
    body = tube(20, 14, 15, builder=b, feature_id="spacer", base_z=10)
    add(body)
result = bp.part
```