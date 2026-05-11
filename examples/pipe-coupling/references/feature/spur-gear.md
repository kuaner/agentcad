# spur_gear(teeth, module, thickness)

Involute spur gear with optional shaft hole.

```python
from agentcad.features import spur_gear

gear = spur_gear(teeth=16, module=2, thickness=6, builder=b, feature_id="drive_gear")
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `teeth` | int | required | Number of gear teeth (minimum 6) |
| `module` | float | required | Pitch diameter / teeth (mm). ISO metric module. |
| `thickness` | float | required | Gear face width along axis (mm) |
| `shaft_diameter` | float | 0 | Central shaft hole diameter (mm). 0 = solid. |
| `pressure_angle` | float | 20 | Involute pressure angle (degrees). ISO standard = 20. |
| `clearance` | float | 0.25 | Root clearance factor (fraction of module) |
| `backlash` | float | 0 | Tooth thickness reduction (mm) |
| `center` | tuple[float, float] | (0, 0) | XY center position |
| `base_z` | float | 0 | Z position of the base |
| `builder` | ContractBuilder | None | Register checks |
| `feature_id` | str | "spur_gear" | Feature/check ID prefix |

## Key Radius Relationships

| Radius | Formula | Description |
|---|---|---|
| Pitch radius | `module * teeth / 2` | Where teeth mesh |
| Base radius | `pitch_radius * cos(pressure_angle)` | Involute generating circle |
| Tip radius | `pitch_radius + module` | Outer tooth tip circle |
| Root radius | `pitch_radius - (1 + clearance) * module` | Bottom of tooth valley |

## Auto-generated Checks

| Check ID | Type | When |
|---|---|---|
| `{id}_bbox` | `bbox_size` | always |
| `{id}_tip_od` | `outer_diameter_at_z` | always (tip circle diameter) |
| `{id}_shaft_id` | `inner_diameter_at_z` | if shaft_diameter > 0 |

## Usage

```python
from build123d import BuildPart, add
from agentcad.features import ContractBuilder, spur_gear

b = ContractBuilder()
with BuildPart() as bp:
    gear = spur_gear(teeth=16, module=2, thickness=6, shaft_diameter=5, builder=b, feature_id="gear")
    add(gear)
result = bp.part
```

The gear uses true involute tooth profiles for accurate meshing. Two gears mesh correctly when they share the same `module` and `pressure_angle`, and their center distance equals the sum of their pitch radii.

For meshing pairs, apply `backlash` to one or both gears to ensure clearance between meshing teeth (typically 0.05-0.1 mm for 3D-printed gears).