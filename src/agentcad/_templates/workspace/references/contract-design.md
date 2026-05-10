# Contract Design

Use this reference when writing or revising `models/<name>/design.json`.

`design.json` is the design contract: it records the intended features and the
checks that prove those features exist in the generated model.

## Minimum Structure

```json
{
  "schema": "design-spec.v1",
  "model": "bracket",
  "units": "mm",
  "intent": "L-bracket with two mounting holes",
  "features": [
    {
      "id": "base_plate",
      "intent": "Horizontal mounting plate",
      "checks": ["base_bbox", "watertight"]
    },
    {
      "id": "mounting_holes",
      "intent": "Two M4 clearance holes",
      "checks": ["left_hole_diameter", "right_hole_diameter", "hole_clearance"]
    }
  ],
  "checks": [
    {"id": "base_bbox", "type": "bbox_size", "expected": [60, 40, 5], "tolerance": 0.3},
    {"id": "watertight", "type": "watertight", "expected": true}
  ]
}
```

## Schema Rules

- Every check must have a unique `id`.
- Every check `type` must be a supported check type.
- Feature `checks` arrays must reference existing check ids.
- Every requested feature must appear in `features`.
- Every feature must link at least one geometry check, not only bbox,
  watertight, artifact, or metadata checks.

## Check Types

| Check type | What it verifies |
|---|---|
| `bbox_size` | Bounding box dimensions within tolerance |
| `watertight` | STL mesh has no boundary edges |
| `min_triangles` | Minimum triangle count |
| `artifact_exists` | File exists at path relative to model dir |
| `metadata_equals` | Value in `metadata.json` matches expected |
| `outer_diameter_at_z` | Outer diameter at a Z section plane |
| `inner_diameter_at_z` | Inner diameter at a Z section plane |
| `diameter_decreases_along_z` | Diameter monotonically decreases over Z range |
| `volume_range` | Volume within min/max bounds |
| `section_bbox_at_z` | XY region at Z is `solid` or `void` |
| `section_component_count` | Number of disconnected contours in an X/Y/Z section |
| `min_clearance` | Edge-to-edge gap between declared shapes |
| `hole_accessibility` | Tool envelope can reach a hole on an X/Y/Z approach plane |
| `min_wall_thickness` | Minimum wall thickness in a region |
| `feature_position` | A point is expected `solid` or `void` |
| `feature_coverage` | Automatic feature-to-check coverage |

## Shape Descriptors

Relational checks such as `min_clearance` consume shape descriptors. Supported
shapes are axis-aligned boxes and cylinders.

```json
{"type": "cylinder", "axis": "z",
 "center": [-15.0, 15.0], "radius": 2.25,
 "z_range": [0.0, 4.0]}

{"type": "cylinder", "axis": "y",
 "center": [0.0, 20.0],
 "radius": 2.25,
 "y_range": [16.0, 20.0]}

{"type": "box",
 "x_range": [-25.0, 25.0],
 "y_range": [16.0, 20.0],
 "z_range": [0.0, 30.0]}
```

Full `min_clearance` example:

```json
{
  "id": "left_hole_wall_clearance",
  "type": "min_clearance",
  "feature_a": {"type": "cylinder", "axis": "z",
                "center": [-15.0, 15.0], "radius": 2.25,
                "z_range": [0.0, 4.0]},
  "feature_b": {"type": "box",
                "x_range": [-25.0, 25.0],
                "y_range": [16.0, 20.0],
                "z_range": [0.0, 30.0]},
  "min_mm": 0.0
}
```

The reported `actual_mm` is the edge-to-edge distance: negative means
interference, zero means touching, positive means clearance.

## Common Design Errors

| Error | Symptom | Prevention |
|---|---|---|
| Hole-wall interference | Hole edge is buried under adjacent solid | Add `min_clearance` between the hole cylinder and adjacent box |
| Hole-edge break | Hole too close to part edge creates C-shaped opening | Add `min_clearance` to the external edge or edge guard |
| Hole-to-hole punch-through | Holes overlap or leave too little wall between them | Add pairwise `min_clearance` using wall thickness as `min_mm` |
| Rib obstructs assembly hole | Bolt fits but tool cannot turn | Add `hole_accessibility` |
| Wall too thin | Printed or machined wall is fragile | Add `min_wall_thickness` |
| Blind hole too shallow | Bolt bottoms out | Add `feature_position` at the hole bottom |
| Feature in wrong direction | Geometry validates locally but function is wrong | Add `feature_position` along the intended axis |
| Feature body exists but root is floating or edge-only | Side/top/front view shows a detached lip, rib, boss, arm, or tab | Add an interface/root check at the attachment plane |
| bbox passes but interior is wrong | Outer envelope is correct but cutouts are missing | Add section, diameter, clearance, or position checks |

Hard rules:

1. Every hole needs a `min_clearance` check for each surrounding wall or
   adjacent solid.
2. Every hole needs a `hole_accessibility` check on the actual tool/fastener
   approach plane. For X/Y-axis holes, set `axis` and the plane coordinate.
3. Every load-bearing attached feature needs a root/interface check. Body
   existence alone is weak evidence.
4. Reason edge-to-edge, never center-to-face.
5. Every feature has at least one geometry check.
6. Resolve weak-check warnings before proceeding.

## Attachment / Connection Checks

For load-bearing features, validate both the body and the attachment. The e2e
cable-hook failure showed why: a front lip can exist and still be effectively
floating in side view if it only touches the arm at a thin edge.

Pattern:

```json
{
  "id": "front_lip_solid",
  "type": "section_bbox_at_z",
  "z": 28.0,
  "region": [[-11.0, -40.5], [11.0, -35.0]],
  "expected": "solid"
},
{
  "id": "front_lip_base_connected",
  "type": "section_bbox_at_z",
  "z": 16.0,
  "region": [[-11.0, -40.5], [11.0, -35.0]],
  "expected": "solid"
}
```

Name these checks with words like `base`, `root`, `interface`, `connected`, or
`junction` so the review trail is obvious.

## Fix Suggestions with `param_ref`

Checks accept an optional `param_ref` field that links the check to a key in
`params.json`. When the check fails, `agentcad validate` generates a targeted
fix suggestion with the current param value, a suggested value, and a confidence
level.

```json
{
  "id": "hole_diameter",
  "type": "inner_diameter_at_z",
  "z": 2.5,
  "expected": 5.0,
  "tolerance": 0.3,
  "center": [0, 0],
  "param_ref": "hole_diameter"
}
```

When this check fails with `actual=4.2` and `hole_diameter` is `4.0` in
`params.json`, the validation output includes:

```json
{
  "suggested_fix": {
    "param": "hole_diameter",
    "current": 4.0,
    "suggested": 4.8,
    "confidence": "high",
    "reason": "inner_diameter_at_z actual=4.2 target=5.0 delta=0.800"
  }
}
```

Without `param_ref`, the fix is a generic action string. Adding `param_ref` to
checks that directly correspond to tunable dimensions makes the iteration loop
faster and more reliable.
