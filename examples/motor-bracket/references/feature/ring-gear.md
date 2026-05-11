# ring_gear(teeth, module, thickness)

Internal involute ring gear. Teeth protrude inward from the root circle toward the tip circle, inside a solid outer rim annulus. Complement to `spur_gear`.

```python
from agentcad.features import ring_gear

gear = ring_gear(20, 2, 5, rim_width=6, builder=b, feature_id="ring")
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `teeth` | int | — | Number of gear teeth (minimum 6) |
| `module` | float | — | Pitch diameter / teeth (mm) |
| `thickness` | float | — | Gear face width (mm) |
| `rim_width` | float or None | module*3 | Outer rim width beyond root circle |
| `pressure_angle` | float | 20 | Involute pressure angle (degrees) |
| `clearance` | float | 0.25 | Root clearance factor |
| `backlash` | float | 0 | Tooth thickness reduction (mm) |
| `center` | tuple[float, float] | (0, 0) | XY center position |
| `base_z` | float | 0 | Z position of the base |
| `builder` | ContractBuilder | None | Register checks |
| `feature_id` | str | "ring_gear" | Feature/check ID prefix |

## Gear Geometry

- **Pitch radius**: `module * teeth / 2`
- **Root radius** (outer boundary of teeth): `pitch + (1+clearance)*module`
- **Tip radius** (innermost point of teeth): `pitch - module`
- **Outer radius**: `root + rim_width`

## Auto-generated Checks

| Check ID | Type | When |
|---|---|---|
| `{id}_od` | `outer_diameter_at_z` | always (outer rim diameter) |
| `{id}_id` | `inner_diameter_at_z` | always (tip circle diameter) |

## Usage

```python
from agentcad.features import ContractBuilder, spur_gear, ring_gear

b = ContractBuilder(intent="gear pair")
outer = spur_gear(12, 2, 5, shaft_diameter=6, builder=b, feature_id="drive")
inner = ring_gear(24, 2, 5, rim_width=8, builder=b, feature_id="annulus")
# Mesh: ring_gear teeth = spur_gear teeth * ratio
```