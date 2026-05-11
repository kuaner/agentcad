# hex_panel(size, strut, spacing)

Honeycomb-core lightweight panel. Returns a positive solid with hexagonal cells cut out.

```python
from agentcad.features import hex_panel

panel = hex_panel((80, 60), strut=1, spacing=8, builder=b, feature_id="light_panel")
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `size` | tuple | required | (width, depth) or (width, depth, height). Height defaults to strut if omitted. |
| `strut` | float | required | Hex cell wall thickness (mm). Also default panel height. |
| `spacing` | float | required | Center-to-center distance between hex cells (mm). |
| `frame` | float | None | Solid frame border width (mm). Default = strut. |
| `center` | tuple[float, float] | (0, 0) | XY center position |
| `base_z` | float | 0 | Z position of the base |
| `builder` | ContractBuilder | None | Register checks |
| `feature_id` | str | "hex_panel" | Feature/check ID prefix |

## Auto-generated Checks

| Check ID | Type | When |
|---|---|---|
| `{id}_bbox` | `bbox_size` | always |
| `{id}_volume` | `volume_range` | always (15-85% of solid volume) |

## Usage

```python
from build123d import BuildPart, add
from agentcad.features import ContractBuilder, hex_panel

b = ContractBuilder()
with BuildPart() as bp:
    panel = hex_panel((80, 60, 3), strut=1, spacing=8, builder=b, feature_id="panel")
    add(panel)
result = bp.part
```

The panel volume is significantly less than a solid rectangle because the hex cells are subtracted. The `volume_range` check verifies that at least 15% of the solid volume remains (strut walls + frame) but no more than 85% (cells must be cut).