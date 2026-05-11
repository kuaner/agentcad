# wedge(width, depth, height)

Triangular prism (gusset, support, angled bracket). Returns a positive solid.

```python
from agentcad.features import wedge

gusset = wedge(30, 10, 15, direction="+x", builder=b, feature_id="gusset")
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `width` | float | required | Extrusion width (mm) — runs along the direction axis |
| `depth` | float | required | Base depth of the cross-section (mm) |
| `height` | float | required | Height of the cross-section along Z (mm) |
| `direction` | str | "+x" | Extrusion direction: "+x", "-x", "+y", "-y" |
| `builder` | ContractBuilder | None | Register checks |
| `feature_id` | str | "wedge" | Feature/check ID prefix |

## Auto-generated Checks

| Check ID | Type | When |
|---|---|---|
| `{id}_bbox` | `bbox_size` | always |

## Usage

```python
from build123d import BuildPart, add, Location
from agentcad.features import ContractBuilder, wedge

b = ContractBuilder()
with BuildPart() as bp:
    gusset = wedge(8, 15, 10, direction="+x", builder=b, feature_id="gusset")
    add(gusset.moved(Location((35, 0, 0))))
result = bp.part
```

Direction determines which axis the extrusion width runs along:
- `"+x"` / `"-x"` — width along X, depth along Y
- `"+y"` / `"-y"` — width along Y, depth along X