# teardrop(diameter, height)

FDM-printable horizontal hole shape. Returns a positive solid — subtract it from your part to create a hole that doesn't need support material.

```python
from agentcad.features import teardrop

hole = teardrop(diameter=6, height=40, angle=45, builder=b, feature_id="cable_hole")
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `diameter` | float | required | Hole diameter (mm) |
| `height` | float | required | Extrusion length / hole depth (mm) |
| `angle` | float | 45 | Overhang angle from vertical in degrees (lower = less overhang, narrower tip) |
| `center` | tuple[float, float] | (0, 0) | XY center position |
| `base_z` | float | 0 | Z position of the base |
| `builder` | ContractBuilder | None | Register checks |
| `feature_id` | str | "teardrop" | Feature/check ID prefix |

## Auto-generated Checks

| Check ID | Type | When |
|---|---|---|
| `{id}_inner` | `inner_diameter_at_z` | always |

## Usage

```python
from build123d import BuildPart, add, Location, Mode
from agentcad.features import ContractBuilder, teardrop

b = ContractBuilder()
with BuildPart() as bp:
    # ... build your part ...
    hole = teardrop(6, 40, angle=45, builder=b, feature_id="cable_hole")
    add(hole.moved(Location((0, 0, 5))), mode=Mode.SUBTRACT)
result = bp.part
```

The teardrop cross-section combines a semicircle (bottom) with a tapered tip (top) at the specified angle. At 45 degrees, the overhang stays within typical FDM limits without support material.