# CADBench Failure-Mode Cookbook

This directory contains small failure-mode fixtures for evaluating whether an
agent turns design intent into checks before modeling.

Each case documents:

- the prompt pattern that commonly fails
- the failure mode
- the required evidence columns
- the check types that should catch the issue

The goal is not visual variety. The goal is false-pass prevention.

## Cases

| Case | Failure Mode | Required Evidence | Correct Checks |
| --- | --- | --- | --- |
| `shallow-hole` | Blind hole too shallow or sampled only at the mouth | position, dimensions | `inner_diameter_at_z`, `feature_position`, targeted probe near bottom |
| `edge-breakout` | Screw/bore center too close to outer edge | position, dimensions, interface risk | `min_clearance`, `hole_accessibility`, point probe to nearest contour |
| `thin-wall` | Slot/hole leaves fragile wall | wall, dimensions | `min_wall_thickness` over the risky region |
| `suspended-rib` | Rib floats or misses parent root | position, wall | root `feature_position`, `min_wall_thickness` |
| `assembly-eccentricity` | Mating axes are offset between parts | position, interface risk | assembly `cylindrical_mate`, `radial_clearance`, `coaxial` |

Run the relevant tests with:

```bash
uv run pytest tests/test_cadbench.py -q
```
