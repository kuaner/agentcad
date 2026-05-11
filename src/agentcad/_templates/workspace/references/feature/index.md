# Feature Library Index

Feature helpers generate build123d geometry **and** auto-write matching feature
+ check entries into `design.json`. Read each helper doc only when you need it.

## Core Pattern

```python
from build123d import BuildPart, add, subtract
from agentcad.features import ContractBuilder, plate, mounting_pattern

b = ContractBuilder(intent="L-bracket")

with BuildPart() as bp:
    plank = plate(60, 40, 5, builder=b, feature_id="base")
    add(plank)
    holes = mounting_pattern("M4", kind="square", spacing=30, depth=5, builder=b)
    subtract(holes)

result = bp.part
b.write_to(project, "bracket")  # merge features + checks into design.json
```

Run `agentcad validate <name>` — auto-generated checks run alongside manual checks.

## Available Helpers

| Helper | What it makes | Reference doc |
|---|---|---|
| `plate` | Flat rectangular plate | `references/feature/plate.md` |
| `mounting_pattern` | Bolt hole array | `references/feature/mounting-pattern.md` |
| `stepped_bore` | Through-hole + counterbore | `references/feature/stepped-bore.md` |
| `boss` | Raised cylinder | `references/feature/boss.md` |
| `rib` | Reinforcing thin wall | `references/feature/rib.md` |
| `duct_socket` | Cylindrical pipe socket | `references/feature/duct-socket.md` |
| `slot` | Rectangular channel | `references/feature/slot.md` |

## Hardware Database

Look up real ISO/DIN dimensions for screws, nuts, washers, inserts.

```python
from agentcad.hardware import screw, nut, washer, insert

s = screw("M3")        # → M3_cap
n = nut("M4")          # → M4_nut
w = washer("M3_penny") # → penny washer
i = insert("F1BM3")    # → heat-set insert
```

Full specs: `references/feature/hardware.md`

## ContractBuilder API

```python
from agentcad.features import ContractBuilder

b = ContractBuilder(intent="description")
b.add(feature={"id": "x", "description": "..."}, checks=[...])
b.write_to(project, model_name)   # merge into design.json
```

- `add(feature, checks)` — register one feature + checks
- `add_feature(feature)` / `add_check(check)` — register individually
- `to_design()` — returns design.json dict
- `write_to(project, name, merge=True)` — write/merge into design.json
- Duplicate IDs raise `ValueError`
