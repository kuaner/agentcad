# nema_mount(size, depth)

NEMA stepper motor mounting hole pattern. Returns a subtractive Part with a center bore and 4 corner mounting holes matching the NEMA standard.

```python
from agentcad.features import nema_mount

holes = nema_mount(17, depth=5, builder=b, feature_id="n17_mount")
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `size` | int | 17 | NEMA motor size: 8, 11, 14, 17, or 23 |
| `depth` | float | 5.0 | Hole depth in mm |
| `center` | tuple[float, float] | (0, 0) | XY center position (motor center) |
| `base_z` | float | 0 | Z position of the hole entry face |
| `builder` | ContractBuilder | None | Register checks |
| `feature_id` | str | "nema_mount" | Feature/check ID prefix |

## NEMA Specs

| Size | Frame (mm) | Bore (mm) | Screw Ø (mm) | Spacing (mm) | Shaft (mm) |
|---|---|---|---|---|---|
| 8 | 20.3 | 16 | 2 | 15.4 | 4 |
| 11 | 28.2 | 22 | 2.6 | 23.11 | 5 |
| 14 | 35.2 | 22 | 3 | 26 | 5 |
| 17 | 42.3 | 22 | 3 | 31 | 5 |
| 23 | 57 | 38.1 | 5.1 | 47 | 6.35 |

## Auto-generated Checks

| Check ID | Type | When |
|---|---|---|
| `{id}_bore` | `inner_diameter_at_z` | always (center bore diameter) |
| `{id}_screw` | `inner_diameter_at_z` | always (corner screw hole diameter) |

## Usage

```python
from build123d import BuildPart, add, subtract
from agentcad.features import ContractBuilder, plate, nema_mount

b = ContractBuilder(intent="motor bracket")
with BuildPart() as bp:
    plank = plate(50, 50, 8, builder=b, feature_id="base")
    add(plank)
    holes = nema_mount(17, depth=8, builder=b, feature_id="n17_mount")
    subtract(holes)

result = bp.part
b.write_to(project, "bracket")
```