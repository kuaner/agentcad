# screw(spec, length)

Screw/bolt 3D visual geometry for assembly visualization. Unlike `screw_hole` (subtractive cut), this returns positive geometry.

```python
from agentcad.features import screw

bolt = screw("M3", length=12, builder=b, feature_id="m3_bolt")
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `spec` | str or Screw | "M3" | Screw specification ("M3", "M3_cap", "M5_pan", etc.) |
| `length` | float | 12.0 | Shaft length in mm (head height not included) |
| `center` | tuple[float, float] | (0, 0) | XY center position (screw axis) |
| `base_z` | float | 0 | Z position of shaft base (threaded end) |
| `builder` | ContractBuilder | None | Register checks |
| `feature_id` | str | "screw" | Feature/check ID prefix |

## Auto-generated Checks

| Check ID | Type | When |
|---|---|---|
| `{id}_head` | `outer_diameter_at_z` | always (head diameter at mid-head height) |
| `{id}_shaft` | `outer_diameter_at_z` | always (shaft diameter at mid-shaft height) |

## Head Styles

The hardware database supports 7 head styles: cap, pan, cs (countersunk), cs_cap, hex, grub, dome. Passing a bare M-size defaults to cap head.

## Usage

```python
from build123d import BuildPart, add
from agentcad.features import ContractBuilder, screw, screw_hole

b = ContractBuilder(intent="bolt assembly")
bolt = screw("M3_cap", length=16, builder=b, feature_id="m3_bolt")
# Use screw_hole for the matching subtractive hole pattern
```