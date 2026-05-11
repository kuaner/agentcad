# nut_body(spec)

Hex nut 3D solid for assembly visualization. Unlike `nut_trap` (subtractive pocket), this returns a positive nut geometry.

```python
from agentcad.features import nut_body

nut = nut_body("M3", builder=b, feature_id="m3_nut")
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `spec` | str or Nut | "M3" | Nut specification ("M3", "M4", "M5", etc.) |
| `center` | tuple[float, float] | (0, 0) | XY center position |
| `base_z` | float | 0 | Z position of the base |
| `builder` | ContractBuilder | None | Register checks |
| `feature_id` | str | "nut" | Feature/check ID prefix |

## Auto-generated Checks

| Check ID | Type | When |
|---|---|---|
| `{id}_section` | `section_bbox_at_z` | always (hex cross-section size) |
| `{id}_bore` | `inner_diameter_at_z` | always (thread bore diameter) |

## Usage

```python
from build123d import BuildPart, add, subtract
from agentcad.features import ContractBuilder, nut_body, nut_trap

b = ContractBuilder()
with BuildPart() as bp:
    # Visual nut for assembly preview
    nut = nut_body("M3", builder=b, feature_id="m3_nut")
    add(nut)
result = bp.part
```

Dimensions come from the hardware database (`agentcad.hardware.nuts`). For creating a nut pocket in your part, use `nut_trap` instead.