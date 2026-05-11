# prismoid(size_bottom, size_top, height)

Tapered box with different top/bottom dimensions. Returns a positive solid.

```python
from agentcad.features import prismoid

base = prismoid((80, 60), (70, 50), 10, builder=b, feature_id="tapered_base")
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `size_bottom` | tuple[float, float] | required | (width, depth) of bottom face (mm) |
| `size_top` | tuple[float, float] | required | (width, depth) of top face (mm) |
| `height` | float | required | Prism height along Z (mm) |
| `center` | tuple[float, float] | (0, 0) | XY center position |
| `base_z` | float | 0 | Z position of the base |
| `rounding` | float | 0 | Edge rounding radius for vertical edges |
| `builder` | ContractBuilder | None | Register checks |
| `feature_id` | str | "prismoid" | Feature/check ID prefix |

## Auto-generated Checks

| Check ID | Type | When |
|---|---|---|
| `{id}_bbox` | `bbox_size` | always |

## Usage

```python
from build123d import BuildPart, add
from agentcad.features import ContractBuilder, prismoid

b = ContractBuilder()
with BuildPart() as bp:
    base = prismoid((80, 60), (70, 50), 10, builder=b, feature_id="base")
    add(base)
result = bp.part
```

For uniform sizing (straight box), set `size_top` equal to `size_bottom`.