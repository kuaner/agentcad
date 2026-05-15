# edge_access_bracket Concept

## Discovery Table

| Field | Answer |
|---|---|
| Functional surfaces | Back face of the wall mount plate; top of hook arm where cable load sits; front lip that retains the cable. |
| Interfaces | Two M4 wall fastener holes with top tool access; hook-root joint between plate, arm, and reinforcing ribs. |
| Envelope / keep-out | 64 x 58 x 18 mm overall envelope; screw tool approaches from +Z and must not be blocked by hook geometry. |
| Critical dimensions | Base 64 x 36 x 4 mm; hole spacing 44 mm; hole diameter 4.5 mm; hook projection 34 mm past the plate; minimum wall/rib thickness 2.4 mm. |
| Failure modes | Edge breakout at mounting holes; blocked screw access; hook arm detached or edge-only connected; ribs floating; lip too thin. |
| Evidence plan | `min_clearance` for hole-to-edge; `hole_accessibility` above plate; `inner_diameter_at_z`; `feature_position` and `section_bbox_at_z` for roots; `min_wall_thickness` for hook/ribs/lip; orthographic preview and review gates. |

## Concept Options

### A. Flat plate with a simple straight hook
- Fastest to print and easiest to model.
- Fails load path: the cantilever root has little reinforcement.
- Checks would prove hole diameter and bbox, but root failure could still look plausible.

### B. Single-piece wall plate, cantilever hook, two root ribs
- Keeps the model one printable piece while adding a clear load path.
- Tool access remains measurable because the mounting holes are behind the hook root.
- Checks can directly cover edge breakout, access, root connection, and wall thickness.

### C. Two-piece screw-on hook insert
- Better serviceability, but assembly fit would dominate the test.
- Adds assembly complexity that distracts from validating the single-model workflow.

Chosen: B. It exercises the standard single-model workflow with multiple real
failure modes while remaining small enough to inspect through sections and
orthographic previews.
