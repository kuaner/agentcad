# torus(major_radius, minor_radius)

Donut ring shape. Built by lofting circular cross-sections around the ring path.

```python
from agentcad.features import torus

ring = torus(major_radius=10, minor_radius=3, builder=b, feature_id="seal_ring")
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `major_radius` | float | required | Ring radius — center of torus to center of tube (mm) |
| `minor_radius` | float | required | Tube radius — cross-section thickness (mm) |
| `center` | tuple[float, float] | (0, 0) | XY center position |
| `base_z` | float | 0 | Z position of center (torus is vertically centered) |
| `builder` | ContractBuilder | None | Register checks |
| `feature_id` | str | "torus" | Feature/check ID prefix |

## Auto-generated Checks

| Check ID | Type | When |
|---|---|---|
| `{id}_od` | `outer_diameter_at_z` | always (major + minor) * 2 |
| `{id}_id` | `inner_diameter_at_z` | always (major - minor) * 2 |

## Usage

```python
from build123d import BuildPart, add
from agentcad.features import ContractBuilder, torus

b = ContractBuilder()
with BuildPart() as bp:
    ring = torus(major_radius=10, minor_radius=3, builder=b, feature_id="seal")
    add(ring)
result = bp.part
```

The torus is approximately V = 2π²·R·r² (where R = major_radius, r = minor_radius). The lofted approximation is within 5-10% of the exact value depending on the ring proportions.