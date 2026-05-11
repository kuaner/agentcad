# rect_tube(size, wall)

Rectangular hollow tube. Outer box minus inner cavity.

```python
from agentcad.features import rect_tube

tube = rect_tube((40, 30, 20), wall=2, builder=b, feature_id="enclosure")
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `size` | tuple | required | (width, depth, height) outer dimensions (mm) |
| `wall` | float | required | Wall thickness on each side (mm) |
| `center` | tuple[float, float] | (0, 0) | XY center position |
| `base_z` | float | 0 | Z position of the base |
| `builder` | ContractBuilder | None | Register checks |
| `feature_id` | str | "rect_tube" | Feature/check ID prefix |

## Auto-generated Checks

| Check ID | Type | When |
|---|---|---|
| `{id}_bbox` | `bbox_size` | always |
| `{id}_id` | `inner_diameter_at_z` | always (measures inner width) |

## Usage

```python
from build123d import BuildPart, add
from agentcad.features import ContractBuilder, rect_tube

b = ContractBuilder()
with BuildPart() as bp:
    enclosure = rect_tube((40, 30, 20), wall=2, builder=b, feature_id="box")
    add(enclosure)
result = bp.part
```

The inner cavity is (width - 2*wall) × (depth - 2*wall), open at top and bottom. Use for enclosures, channels, and housing frames.