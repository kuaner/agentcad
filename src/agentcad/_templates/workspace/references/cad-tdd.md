# CAD TDD

Use this reference before writing `part.py`.

Every feature must have a check that can pass or fail before the final geometry
is written. The order is not negotiable: checks first, geometry second.

## Per-Feature Planning Table

Fill this table before implementing a feature:

| Feature | Shape | Center (cx, cy) | Z slice | Expected value | Check type |
|---|---|---|---|---|---|
| Outer shell | rectangle | - | - | [w, h, t] | `bbox_size` |
| Camera hole | W x H rectangle | (cx, cy) | wall_back / 2 | min(W, H) | `inner_diameter_at_z` |
| Inner cavity | void | center | wall_back + 2 | `void` | `section_bbox_at_z` |
| USB-C port | W x H rectangle | (0, y) | z_mid | min(W, H) | `inner_diameter_at_z` |

If you cannot fill in all columns for a feature, ask a focused question or
revise the contract before coding. Do not start `part.py` while a feature has
no measurable check strategy.

## Red Phase

After finishing `design.json`, write a minimal `part.py` that produces the
outer envelope only, no internal features. Then run:

```bash
agentcad validate <model>
```

Expected outcome:

- `bbox_size` passes.
- Section, diameter, clearance, or position checks for missing internal
  features fail.

If a section check passes while its feature is missing, the check is wrong.
Return to the planning table and redesign it.

## Green Phase

Implement one feature at a time and rerun `agentcad validate` immediately.
Watch the matching check flip from failing to passing. Do not batch multiple
features before validating.

## Iteration Loop with Fix Suggestions and Diff

When `agentcad validate` fails, each failing check includes a `suggested_fix`
object:

1. If `suggested_fix.confidence` is `"high"` and a `param` key is provided,
   update that param in `params.json` to the `suggested` value.
2. If `suggested_fix.confidence` is `"low"`, the param may not directly control
   the dimension. Inspect the geometry before changing params.
3. Re-run `agentcad validate <model>`.
4. Run `agentcad diff <model>` to see which checks were fixed, which regressed,
   and whether geometry drifted between iterations.

## Model Variants

To test the same geometry with different dimensions:

```bash
agentcad new <model>:small
# Edit models/<model>/variants/small/params.json
agentcad validate <model>:small
```

Variants share `part.py` and `design.json` with the base model. Only
`params.json` differs. Variant outputs go to `models/<model>/outputs/<variant>/`.

Use `model:variant` syntax with any command: `build`, `validate`, `preview`,
`deliver`.

## Feature To Check Cheat Sheet

| Feature type | Check type | Z slice | Expected value | Tolerance |
|---|---|---|---|---|
| Circular hole diameter D | `inner_diameter_at_z` | mid-Z of hole | D | 0.3 |
| Rectangular hole W x H | `inner_diameter_at_z` | mid-Z of hole | min(W, H) | 3-5 |
| Rectangular void region | `section_bbox_at_z` expected=`void` | mid-Z of feature | - | - |
| Solid face, boss, or back panel | `section_bbox_at_z` expected=`solid` | mid-Z of face | - | - |
| Outer envelope | `bbox_size` | - | [total_w, d, h] | 0.5 |
| Taper or lead-in | `diameter_decreases_along_z` | z_range | monotonic | - |
| Hole vs adjacent solid | `min_clearance` | - | descriptors | min_mm=0 |
| Bolt assembly hole | `hole_accessibility` | working plane Z | hole and clearance radius | - |
| Thin wall or rib | `min_wall_thickness` | section Z | min_mm=1.0 | 0.1 |
| Direction marker | `feature_position` | point | `solid` or `void` | 0.5 |
| Attached lip/rib/boss/arm root | `section_bbox_at_z` | attachment/interface Z | `solid` | - |

Z slice formula: if a feature occupies `[z_bottom, z_top]`, slice at
`z = (z_bottom + z_top) / 2`.

When you do not know the expected value, run `agentcad build`, then
`agentcad probe <model> --z <z>`. The `suggested_checks` field is ready to
paste into `design.json`.

When you do not know which Z to probe, run `agentcad probe <model> --scan` to
surface step changes such as cavity starts and wall transitions.

## Connection Red Phase

For attached features, write two checks before coding:

- body check: the feature exists at its main section
- root check: the feature has material at the interface where it must transfer
  load into the parent body

In the red phase, deliberately build only the parent body and confirm both
checks fail. In the green phase, make sure the root check flips only when the
feature is actually connected through a meaningful contact area.
