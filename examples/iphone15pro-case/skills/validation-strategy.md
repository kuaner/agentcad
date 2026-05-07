# Validation Strategy & Troubleshooting

## design.json Structure

```json
{
  "schema": "design-spec.v1",
  "model": "bracket",
  "units": "mm",
  "intent": "What this part does",
  "features": [
    {
      "id": "feature_id",
      "intent": "What this feature is for",
      "checks": ["check_id_1", "check_id_2"]
    }
  ],
  "checks": [
    { "id": "check_id_1", "type": "bbox_size", ... }
  ]
}
```

Every feature must reference at least one existing check ID. The validator
enforces feature-to-check coverage automatically.

## Choosing Check Types

### Overall envelope
- `bbox_size` — bounding box dimensions with tolerance
- `volume_range` — volume within min/max range
- `watertight` — manifold mesh (no boundary edges)

### Artifact presence
- `artifact_exists` — file exists at the given path (relative to model dir)

### Holes and circular features
- `inner_diameter_at_z` — diameter of the innermost boundary at a Z section plane
- `outer_diameter_at_z` — diameter of the outermost boundary at a Z section plane
- Both accept `center` parameter to check off-axis holes (e.g., bolt holes at corners)
- These use STL triangle-plane intersection

### Tapers, chamfers, and sockets
- `diameter_decreases_along_z` — monotonic diameter change across Z samples
- Combine with `outer_diameter_at_z` at key Z values for both-end verification

### Design intent metadata
- `metadata_equals` — check a path in metadata.json matches expected value
- Use as supplementary evidence, never as the sole check for a feature

### Mesh quality
- `min_triangles` — minimum triangle count (catches degenerate exports)

## Section Checks in Detail

Section checks slice the STL at a given Z height and estimate the radial
envelope around a center point. The `center` parameter `[x, y]` controls where
the measurement is centered — defaults to `[0, 0]`.

### Checking on-axis features (centered at origin)

```json
{
  "id": "socket_od_at_z10",
  "type": "outer_diameter_at_z",
  "z": 10.0,
  "expected": 79.4,
  "tolerance": 0.3,
  "center": [0.0, 0.0]
}
```

### Checking off-axis holes (bolt holes, mounting holes)

Set `center` to the hole position. `inner_diameter_at_z` measures the hole
diameter at that location — the hole wall forms the innermost boundary.

```json
{
  "id": "hole_at_corner",
  "type": "inner_diameter_at_z",
  "z": 5.0,
  "expected": 5.0,
  "tolerance": 0.3,
  "center": [30.0, 20.0]
}
```

For counterbored holes, check at two Z heights:
- Through-hole section (below counterbore): `inner_diameter_at_z` → hole diameter
- Counterbore section: `inner_diameter_at_z` → counterbore diameter

Multiple holes can each have their own check with different `center` values.

### Checking rectangular or camera cutouts

`inner_diameter_at_z` also works for **non-circular cutouts** when `center` is
placed at the cutout's centroid. The inner radius estimate equals the smallest
perpendicular distance from the centroid to the nearest cutout wall.

For a rectangular cutout `W × H` centered at `(cx, cy)`, the inner diameter
≈ `min(W, H)` (the shorter half-dimension × 2). Use `tolerance` of 3–5 mm
to account for the rectangular shape and STL mesh quantization.

```json
{
  "id": "camera_hole",
  "type": "inner_diameter_at_z",
  "z": 0.75,
  "center": [-10.3, 53.3],
  "expected": 39.5,
  "tolerance": 5.0
}
```

This check passes when the hole exists (inner diameter ≈ 39.5 mm) and fails
when the region is solid (inner diameter ≈ 100+ mm from the outer shell).

### Checking that a region is solid (back panel exists)

Use `section_bbox_at_z` to verify that intersection points cover a target XY
rectangle at a given Z. This confirms that a back panel, flange, or shelf is
present at the expected height.

```json
{
  "id": "back_panel_solid",
  "type": "section_bbox_at_z",
  "z": 0.75,
  "region": [[-5.0, -5.0], [5.0, 5.0]],
  "expected": "solid"
}
```

`expected: "solid"` → the region must contain STL intersection points (material present).
`expected: "void"` → the region must have no intersection points (hole or cavity present).

## Tolerance Selection

- 0.1-0.2 mm: tight fit, bearing surfaces, critical mating dimensions
- 0.3-0.5 mm: general mechanical, slip fits, clearance holes
- 0.5-1.0 mm: non-critical, cosmetic, large structural parts
- STL mesh resolution affects measurement precision. Typical export tolerance
  is around 0.01 mm but section checks use percentile estimation which adds
  ~0.1 mm uncertainty. Do not set tolerances below 0.1 mm for section checks.

## Feature Coverage Strategy

1. List every user-visible or functional feature in `features`
2. For each feature, pick the most direct check type
3. If no existing check type can verify it, use `metadata_equals` as a
   placeholder and note the limitation
4. Never leave a feature without at least one check reference

## Check Design Anti-Patterns

- Checking only bbox + watertight: these pass even when features are missing
- Using metadata_equals as the sole check for a geometry feature
- Setting tolerance to 0: STL mesh quantization makes exact matches unreliable
- Not checking both ends of a taper or socket
- Relying on watertight alone to confirm a cutout exists: a solid back panel
  and a back panel with a hole are both watertight — use `inner_diameter_at_z`
  with the cutout center, or `section_bbox_at_z` to verify the geometry directly

## Build Error Troubleshooting

### MissingResult: part.py must define global variable result

The script executed but no `result` variable was found in the global scope.

Fix: ensure the last line of part.py assigns the build123d object:
```python
result = bp.part
```
Do not return it from a function and forget to assign.

### NameError or ImportError

Usually a typo in a build123d API name or a missing import. The full traceback
is in `outputs/build.json` under `stderr`.

Fix: read the stderr field in the build report, fix the name, rerun
`cad validate`.

### build123d topology errors

Messages like "Unable to fuse" or "Null shape" mean the boolean operation
produced invalid geometry.

Common causes:
- Zero-thickness solids (two faces exactly coplanar)
- Subtracting a shape that does not intersect the base solid
- Fillet radius larger than the edge length or adjacent face

Fix: reduce fillet/chamfer size, add a small offset between coplanar faces
(0.01 mm is enough), or change boolean operation order.

## Validation Failure Troubleshooting

### bbox_size fails but geometry looks correct

The default Box alignment is center on all axes. If you used Align.MIN on Z
and the bbox center shifted, the size dimensions may still match. If size is
wrong, check your parameter values in params.json and ensure you are reading
the right keys.

### watertight is false

The STL mesh has boundary edges. Common causes:
- Zero-thickness walls in the CAD model
- Boolean subtraction that left an open shell
- Extremely small features below mesh resolution

Fix: increase wall thickness to at least 0.8 mm, check boolean operations for
correctness.

### feature_coverage fails

Every feature in `design.json.features` must list at least one check ID that
exists in `design.json.checks`. Check for typos in check IDs and ensure every
feature has a non-empty `checks` array.

### Section checks return unexpected diameters

- `center` defaults to [0, 0]. Set it to the feature's actual position for
  off-axis measurements.
- STL triangle density at the section plane affects precision. If the mesh is
  coarse, increase tolerance.
- `diameter_outer_estimate` uses the 98th percentile radius, not the max. This
  filters outlier artifacts but may slightly underreport the true outer
  diameter. Adjust tolerance accordingly (typically 0.2-0.3 mm is safe).
- `diameter_inner_estimate` uses the 2nd percentile of nonzero radii. It picks
  up the nearest boundary around the center point, which is the hole wall for
  correctly centered checks.
