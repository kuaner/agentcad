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
- `outer_diameter_at_z` — section plane intersection, outer diameter estimate
- `inner_diameter_at_z` — section plane intersection, inner diameter estimate
- These use STL triangle-plane intersection, best for axisymmetric geometry

### Tapers, chamfers, and sockets
- `diameter_decreases_along_z` — monotonic diameter change across Z samples
- Combine with `outer_diameter_at_z` at key Z values for both-end verification

### Design intent metadata
- `metadata_equals` — check a path in metadata.json matches expected value
- Use as supplementary evidence, never as the sole check for a feature

### Mesh quality
- `min_triangles` — minimum triangle count (catches degenerate exports)

## Section Checks in Detail

Section checks slice the STL at a given Z height and estimate radial envelope
around a center point. They work best for axisymmetric features (cylinders,
ducts, sockets, tapers).

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

For off-axis holes (e.g., bolt holes at corners), section checks centered at
(0,0) will not work. Use `metadata_equals` to record the design intent and add
a comment that a geometry check for that position is not yet available.

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

- `center` defaults to [0, 0]. If the feature is off-center (e.g., a bolt hole
  at a corner), the section slice will measure the wrong profile.
- STL triangle density at the section plane affects precision. If the mesh is
  coarse, increase tolerance.
- `diameter_outer_estimate` uses the 98th percentile radius, not the max. This
  filters outlier artifacts but may slightly underreport the true outer
  diameter. Adjust tolerance accordingly (typically 0.2-0.3 mm is safe).
