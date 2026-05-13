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

## Feature Evidence Matrix

`agentcad review` evaluates every feature across these evidence columns. A
feature is not ready just because it has one check.

| Evidence column | Required for | Strong check examples |
|---|---|---|
| Position | every feature | `feature_position`, centered diameter check, regional `section_bbox_at_z`, `min_clearance` descriptor |
| Dimensions | every feature | `bbox_size`, `inner_diameter_at_z`, `outer_diameter_at_z`, `section_bbox_at_z`, `min_wall_thickness` |
| Access | holes, bores, screw/bolt paths | `hole_accessibility` on the real approach plane |
| Wall/root | walls, shells, ribs, bosses, tabs, hooks, arms | `min_wall_thickness`, root `section_bbox_at_z`, root `feature_position` |
| Interface risk | holes and mating interfaces | `min_clearance`, interface metadata check, assembly clearance |

Run:

```bash
agentcad suggest-checks <model>
agentcad probe <model> --plan
```

Use the suggested probe plan to choose section planes before guessing `z`,
`center`, or `region` values.

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

## Failure-Mode Cookbook

Use these examples as starting points. Replace values with parameters from
`params.json`.

### Shallow Blind Hole

Failure: the screw starts but bottoms out before clamping.

Correct evidence:

```json
{
  "id": "m3_bore_bottom_void",
  "type": "feature_position",
  "point": [12.0, 8.0, 7.5],
  "expected": "void",
  "tolerance_mm": 0.4
}
```

Also check diameter at mid-depth:

```json
{"id": "m3_bore_diameter", "type": "inner_diameter_at_z",
 "z": 4.0, "center": [12.0, 8.0], "expected": 3.4, "tolerance": 0.3}
```

### Edge Breakout Near A Hole

Failure: the hole is the right diameter but breaks through the part edge.

Correct evidence:

```json
{
  "id": "m3_hole_edge_clearance",
  "type": "min_clearance",
  "feature_a": {"type": "cylinder", "axis": "z",
                "center": [22.0, 0.0], "radius": 1.7,
                "z_range": [0.0, 5.0]},
  "feature_b": {"type": "box", "role": "edge_guard",
                "x_range": [25.0, 26.0],
                "y_range": [-15.0, 15.0],
                "z_range": [0.0, 5.0]},
  "min_mm": 0.0
}
```

### Thin Wall Around A Cavity

Failure: the outer bbox passes, but the shell is too fragile.

Correct evidence:

```json
{
  "id": "case_wall_thickness",
  "type": "min_wall_thickness",
  "axis": "z",
  "range": [1.0, 10.0],
  "samples": 6,
  "region": [[-38.0, -75.0], [38.0, 75.0]],
  "min_mm": 1.2,
  "tolerance": 0.1
}
```

### Suspended Rib Or Tab

Failure: the rib body exists but is floating or only edge-connected.

Correct evidence:

```json
{"id": "rib_body_solid", "type": "section_bbox_at_z",
 "z": 12.0, "region": [[-2.0, 0.0], [2.0, 25.0]], "expected": "solid"}
```

```json
{"id": "rib_root_connected", "type": "section_bbox_at_z",
 "z": 2.0, "region": [[-2.0, 0.0], [2.0, 25.0]], "expected": "solid"}
```

### Assembly Eccentricity

Failure: a pin, socket, lid, fan, duct, gear, or screw axis is offset even
though each part validates alone.

Correct evidence:

```json
{
  "id": "shaft_socket_axis_position",
  "type": "feature_position",
  "point": [0.0, 0.0, 12.0],
  "expected": "void",
  "tolerance_mm": 0.3
}
```

Also emit metadata interfaces with axis point/direction so assembly contracts
can compare the mating axes instead of relying on copied coordinates.

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
