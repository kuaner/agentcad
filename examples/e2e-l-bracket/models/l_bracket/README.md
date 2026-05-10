# l_bracket

AgentCAD model folder.

## Files you edit

- `design.json` — design intent + validation checks (the design contract)
- `params.json` — tunable dimensions
- `part.py` — build123d geometry (must assign final shape to `result`)

## Recommended workflow

```bash
agentcad precheck l_bracket     # 1. solve design.json statically
# write part.py once precheck is green
agentcad build l_bracket        # 2. generate STEP/STL
agentcad measure l_bracket      # 3. measure geometry stats
agentcad validate l_bracket     # 4. run all checks (auto-renders SVGs)
agentcad review l_bracket       # 5. pre-delivery checklist + relations matrix
agentcad deliver l_bracket      # 6. write delivery manifest
```

Before writing `design.json`, run the Discovery Gate in
`../../references/discovery.md`. If mating dimensions, manufacturing target,
tolerances, orientation, or topology choices are unclear, ask 2-3 focused
questions with concrete options and wait for the user's answer.

For non-trivial parts, write a short `concept.md` using
`../../references/concept-design.md` before committing `design.json`. After
`validate` and `review` pass, apply
`../../references/design-quality-review.md` before delivery.

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

Also declare a `hole_accessibility` check for the real approach plane. For a
Y-axis screw driven from the front of a vertical plate, the center is `[x, z]`:

```json
{
  "id": "left_hole_tool_access",
  "type": "hole_accessibility",
  "axis": "y",
  "y": -10.0,
  "center": [hole_x, hole_z],
  "hole_diameter": 4.5,
  "clearance_diameter": 12.0
}
```

For attached load-bearing features, add a connection/root check. A retaining
lip, rib, boss, tab, arm, or flange needs proof that the base interface exists,
not only proof that the feature body exists somewhere.

See `../../references/validation-strategy.md` for a complete catalog of design
errors and the check types that catch them.

Generated artifacts go to `outputs/`.
