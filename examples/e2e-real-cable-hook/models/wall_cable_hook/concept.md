# Concept: Wall-Mounted Cable Hook

## User Goal And Context

Design a practical FDM-printable wall-mounted cable hook for routing a small
power cable or USB cable. The part should screw to a vertical surface, project
forward to hold the cable, and include a retaining lip so the cable cannot
slide off.

Assumptions:

- Units: mm.
- Manufacturing: FDM print in PETG/PLA with 0.4 mm nozzle.
- Fasteners: two M4 or #8 wood-screw clearance holes through the upper left
  and right wings of a vertical back plate.
- General tolerance: 0.3-0.5 mm for printed features.

## Concept Options

### A. Vertical back plate with a straight cantilever shelf

- Best for: fastest geometry and minimal material.
- Risk: the arm-to-plate junction is a sharp bending hotspot and can fail along
  FDM layer lines.
- Validation: back plate bbox, screw hole voids, hook arm section, lip section.

### B. Vertical back plate with boxed hook arm, front lip, and twin web ribs

- Best for: practical printed hook with a clear load path from the lip and arm
  back into the plate.
- Risk: blockier visual form, but stronger and easier to validate.
- Validation: back plate, accessible screw holes, screw-head reliefs, hook
  arm, retaining lip, twin ribs, top/spacing clearances, and artifact checks.

### C. Clip-style U cradle with snap-in cable retainer

- Best for: retaining one known cable diameter.
- Risk: snap-fit dimensions depend on cable size and material flexibility, so
  it needs more user input before it can be responsible.
- Validation: cradle gap, snap clearance, retainer deflection envelope, wall
  thickness.

## Chosen Concept

Choose concept B. It is a credible wall-mounted FDM part and forces the workflow
to reason about topology, wall attachment, fastener holes, support ribs, and
post-validation design quality. Unlike the rejected horizontal-plate concept,
the back plate is vertical and the hook projects forward from it, so no major
functional mass is visually or structurally suspended without support.

## Key Dimensions

- Back plate: 60 mm wide, 50 mm high, 5 mm thick.
- Screw holes: two 4.5 mm through holes at X=-20 mm and X=20 mm, Z=38 mm,
  outside the central hook/rib envelope so the screwdriver path is open.
- Screw-head reliefs: 9 mm diameter by 2 mm deep on the front face.
- Hook arm: 22 mm wide, 35 mm projection, 8 mm thick, with 1 mm overlap into
  the back plate.
- Front retaining lip: 22 mm wide, 6 mm deep, 18 mm high, overlapping the
  hook arm through its full thickness instead of touching only at the top edge.
- Twin support ribs: 4 mm wide each, tied from the hook arm to the back plate.

## Validation Strategy

- Overall bbox and watertightness.
- `feature_position` void checks for both through screw holes and both forward
  screwdriver access corridors.
- `hole_accessibility` checks on a Y-axis approach plane in front of the plate
  for both upper-wing screw holes.
- Void checks for the larger front screw-head reliefs.
- `min_clearance` from the screw holes to the top guard and between holes.
- Section checks for the hook arm, retaining lip body, retaining lip base
  connection, both ribs, and the vertical back plate.
- Artifact checks for STEP and STL.
