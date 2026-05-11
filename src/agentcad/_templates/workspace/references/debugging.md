# Debugging

Use this reference when build, validation, review, or build123d API work gets
stuck.

## First Rule

Read the JSON report before guessing. Failures include a stage, error type,
message, and usually an artifact path.

Important reports:

- `models/<name>/outputs/build.json`
- `models/<name>/outputs/geometry.json`
- `models/<name>/outputs/precheck.json`
- `models/<name>/outputs/validation.json`
- `models/<name>/outputs/review.json`

## Critical build123d Warnings

### 1. BuildSketch + Locations does not move the sketch plane

`Locations(x, y, z) + BuildSketch(Plane.XY) + extrude` does not place the
sketch at `z`. The sketch stays on its own plane.

```python
# Wrong: sketch stays at Z=0.
with Locations((0, 0, wall_back)):
    with BuildSketch(Plane.XY):
        RectangleRounded(w, h, r)
    extrude(amount=depth, mode=Mode.SUBTRACT)

# Correct: explicit origin positions the plane.
with BuildSketch(Plane(origin=(0, 0, wall_back))):
    RectangleRounded(w, h, r)
extrude(amount=depth, mode=Mode.SUBTRACT)
```

Use `Locations` with 3D primitives such as `Box`, `Cylinder`, and `Cone`. Use
explicit `Plane(origin=(x, y, z))` for `BuildSketch` positioning.

### 2. fuse() + add(mode=SUBTRACT) does not create reliable through-holes

Creating standalone cylinders, fusing them into a single Part, and then using
`add(fused_part, mode=Mode.SUBTRACT)` produces **incomplete boolean cuts**.
The hole appears to start from one face but stops partway through the solid,
even though the cylinder geometry extends past both faces. `inner_diameter_at_z`
at mid-depth passes, giving a false sense of correctness.

```python
# Wrong: hole stops partway through.
holes = []
for px, py in positions:
    with BuildPart(mode=Mode.PRIVATE) as hole:
        Cylinder(radius=r, height=depth, align=(Align.CENTER, Align.CENTER, Align.MIN))
    holes.append(hole.part.moved(Location((px, py, 0))))
fused = holes[0]
for h in holes[1:]:
    fused = fused.fuse(h)
add(fused, mode=Mode.SUBTRACT)

# Correct: subtract each cylinder in-context with overshoot.
overshoot = 1.0
for px, py in positions:
    with Locations((px, py, -overshoot / 2)):
        Cylinder(
            radius=r,
            height=depth + overshoot,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
            mode=Mode.SUBTRACT,
        )
```

**Why overshoot matters:** A cylinder whose height exactly matches the material
thickness leaves paper-thin faces at the entry and exit surfaces. Adding 1mm
overshoot and offsetting the start by 0.5mm ensures the cylinder extends past
both faces for a clean cut.

**How to verify:** Run section checks at Z near the bottom face AND Z near the
top face. A single `inner_diameter_at_z` at mid-depth is not sufficient — it
passes even when the hole only penetrates halfway.

The feature helpers `MountingHoles.cut()` and `SteppedBore.cut()` already use
the correct in-context pattern.

## Common Triage

| Symptom | First action |
|---|---|
| `part.py` runs but build fails | Read `outputs/build.json` stderr |
| `MissingResult` | Assign the final build123d object to global `result` |
| Validate fails after build passes | Read `outputs/validation.json` checks in order |
| A feature appears missing | Run `agentcad inspect <model>` and inspect section SVGs |
| A check passes too early | Fix `design.json`; the check is too weak or pointed at the wrong region |
| Boolean subtraction cuts nothing | Run `agentcad probe <model> --scan` and confirm the step changes |
| Hole collides with wall | Add or fix `min_clearance` descriptors and rerun `agentcad precheck` |
| Review blocks delivery | Read `outputs/review.json` and inspect every `must_view` SVG |

## Querying build123d Documentation

When local references are not enough, fetch the relevant build123d docs page
before guessing.

```text
WebFetch https://build123d.readthedocs.io/en/latest/<page>.html
```

Useful pages:

- `objects`: Box, Cylinder, Cone, Sphere, Torus, Wedge
- `operations`: fillet, chamfer, hole, split, mirror, offset
- `topology_selection`: filter_by, sort_by, group_by
- `tutorial_selectors`: edge and face selection patterns
- `build_part`: BuildPart context manager details
- `build_sketch`: 2D sketch construction
- `moving_objects`: Location, rotation, alignment
- `key_concepts_builder`: Align, Mode, Select enums
- `cheat_sheet`: quick syntax reference
- `general_examples`: real-world model examples
