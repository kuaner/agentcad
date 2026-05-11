# pie_slice(radius, angle, height)

Cylindrical sector wedge (pie slice). Arc segment extruded to 3D.

```python
from agentcad.features import pie_slice

sector = pie_slice(radius=10, angle=90, height=5, builder=b, feature_id="bracket_arc")
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `radius` | float | required | Outer radius (mm) |
| `angle` | float | required | Sector angle in degrees (1-360) |
| `height` | float | required | Height along Z (mm) |
| `center` | tuple[float, float] | (0, 0) | XY center (center of arc) |
| `base_z` | float | 0 | Z position of the base |
| `builder` | ContractBuilder | None | Register checks |
| `feature_id` | str | "pie_slice" | Feature/check ID prefix |

## Auto-generated Checks

| Check ID | Type | When |
|---|---|---|
| `{id}_bbox` | `bbox_size` | always |
| `{id}_volume` | `volume_range` | always (0 to full cylinder volume) |

## Usage

```python
from build123d import BuildPart, add
from agentcad.features import ContractBuilder, pie_slice

b = ContractBuilder()
with BuildPart() as bp:
    sector = pie_slice(radius=10, angle=90, height=5, builder=b, feature_id="arc_wall")
    add(sector)
result = bp.part
```

The sector spans from angle 0° to the given angle, centered at (0,0). Volume ≈ π·r²·h·(angle/360). For angle=360, returns a full cylinder.