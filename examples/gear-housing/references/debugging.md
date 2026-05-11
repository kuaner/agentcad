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

For detailed build123d pitfalls with code examples, see
`references/build123d-guide.md` (pitfalls #8 and #9).

Key warnings to keep in mind:

- **BuildSketch + Locations does not move the sketch plane.** Use
  `Plane(origin=(x, y, z))` explicitly.
- **fuse() + add(mode=SUBTRACT) does not create reliable through-holes.** Use
  `Locations` + `Cylinder(mode=Mode.SUBTRACT)` in-context instead.
- **Always add overshoot to subtraction cylinders** (1mm past both faces).

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
