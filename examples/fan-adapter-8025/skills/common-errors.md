# Common Errors and Fixes

## Build Errors

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

## Validation Failures

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

## Modeling Pitfalls

### Chamfer/fillet hidden by overlapping geometry

A chamfer coded correctly can be visually hidden if a later operation adds a
cylinder or box that overlaps the chamfered region. The geometry is technically
correct but the chamfer serves no purpose.

Prevention: use `outer_diameter_at_z` or `diameter_decreases_along_z` checks
at the chamfer location to verify the surface actually changes.

### Wrong Align causing off-center parts

```python
# This box is centered at origin
Box(40, 30, 20)

# This box starts at Z=0 and extends upward
Box(40, 30, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))
```

Be explicit about alignment. If a flange should sit on top of another part,
use Align.MIN on Z for the base and Align.MIN for the added part, then offset
with `with Locations(...)`.

### Hole depth does not go all the way through

`Hole(radius)` without depth goes through the full part thickness. Specifying
`depth=X` makes it X mm deep from the current workplane. If the workplane is
not where you think it is, the hole may stop short.

Fix: use `Hole(radius)` without depth for through-holes. For blind holes, be
explicit about the workplane location.
