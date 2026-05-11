# mounting_pattern(spec, kind, spacing)

Bolt hole pattern. Returns a **negative** solid (holes) — subtract from parent.

```python
from agentcad.features import mounting_pattern

holes = mounting_pattern("M4", kind="square", spacing=30, depth=5, builder=b)
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `spec` | str or Screw | required | Screw spec: `"M3"`, `"M4_cap"`, `"M3_dome"` |
| `kind` | str | "square" | Pattern type (see below) |
| `spacing` | float | None | Hole spacing for square/linear/circular |
| `spacing_x`, `spacing_y` | float | None | Separate X/Y spacing (rectangular) |
| `count` | int | None | Hole count (linear/circular) |
| `center` | (float, float) | (0,0) | Pattern center in XY |
| `depth` | float | 5 | Hole depth (mm) |
| `through` | bool | True | True = clearance, False = tap |
| `fit` | str | "normal" | `"tight"`, `"normal"`, `"loose"` |
| `approach_axis` | str | "z" | Tool approach axis |
| `builder` | ContractBuilder | None | Register checks |
| `feature_id` | str | "mounting_holes" | ID prefix |

## Pattern Kinds

| Kind | Holes | Required params |
|---|---|---|
| `square` | 4 corners | `spacing` |
| `rectangular` | 4 corners | `spacing_x`, `spacing_y` |
| `linear` | N in a row | `spacing`, `count` |
| `circular` | N on bolt circle | `spacing` (diameter), `count` |

## Auto-generated Checks (per hole)

| Check ID | Type | When |
|---|---|---|
| `{id}_dia{i}` | `inner_diameter_at_z` | always |
| `{id}_access{i}` | `hole_accessibility` | `through=True` |

## Usage

```python
from build123d import BuildPart, add, Mode
from agentcad.features import ContractBuilder, mounting_pattern

b = ContractBuilder()
with BuildPart() as bp:
    # ... create parent body ...
    holes = mounting_pattern("M4", kind="square", spacing=71.5, depth=5, builder=b)
    add(holes, mode=Mode.SUBTRACT)
```
