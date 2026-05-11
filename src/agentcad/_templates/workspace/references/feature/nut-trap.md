# nut_trap(spec, depth)

Hex nut trap pocket. Returns a positive solid — subtract it from your part to create a hex-shaped pocket for nut retention.

```python
from agentcad.features import nut_trap

nt = nut_trap("M3", depth=6, orientation="top", builder=b, feature_id="nut_trap")
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `spec` | str or Screw | required | Screw spec like "M3" — determines nut across-flats size |
| `depth` | float | required | Pocket depth (mm) |
| `orientation` | str | "side" | "side" = nut slides in from the side; "top" = nut drops in from the top |
| `entry_slot_width` | float | 0 | Width of the side-entry slot (mm). 0 = no slot |
| `center` | tuple[float, float] | (0, 0) | XY center position |
| `base_z` | float | 0 | Z position of the pocket base |
| `builder` | ContractBuilder | None | Register checks |
| `feature_id` | str | "nut_trap" | Feature/check ID prefix |

## Auto-generated Checks

| Check ID | Type | When |
|---|---|---|
| `{id}_hex` | `section_bbox_at_z` | always |

## Usage

```python
from build123d import BuildPart, add, Location, Mode
from agentcad.features import ContractBuilder, nut_trap

b = ContractBuilder()
with BuildPart() as bp:
    # ... build your part ...
    nt = nut_trap("M3", depth=5, orientation="top", center=(0, -20), builder=b, feature_id="nut_trap")
    add(nt, mode=Mode.SUBTRACT)
result = bp.part
```

Nut across-flats sizes are auto-computed from the screw spec: M3 → 5.5mm, M4 → 7mm, M5 → 8mm, M6 → 10mm, M8 → 13mm.