# {name}

AgentCAD model folder.

## Files you edit

- `design.json` — design intent + validation checks (the design contract)
- `params.json` — tunable dimensions
- `part.py` — build123d geometry (must assign final shape to `result`)

## Recommended workflow

```bash
agentcad precheck {name} --json     # 1. solve design.json statically
# write part.py once precheck is green
agentcad build {name} --json        # 2. generate STEP/STL
agentcad measure {name} --json      # 3. measure geometry stats
agentcad validate {name} --json     # 4. run all checks (auto-renders SVGs)
agentcad review {name} --json       # 5. pre-delivery checklist + relations matrix
agentcad deliver {name} --json      # 6. write delivery manifest
```

## Common errors to design *against*

For every hole declared in `params.json`, also declare a `min_clearance` check
in `design.json` between the hole cylinder and each adjacent solid (walls,
plates, flanges, edges). This catches the classic "hole edge buried under a
wall" bug at design time, before any code is written.

```json
{
  "id": "hole_X_clearance",
  "type": "min_clearance",
  "feature_a": {"type": "cylinder", "axis": "z",
                "center": [hole_x, hole_y], "radius": hole_r,
                "z_range": [z0, z1]},
  "feature_b": {"type": "box",
                "x_range": [...], "y_range": [...], "z_range": [...]},
  "min_mm": 0.0
}
```

See `../references/validation-strategy.md` for a complete catalog of design
errors and the check types that catch them.

Generated artifacts go to `outputs/`.
