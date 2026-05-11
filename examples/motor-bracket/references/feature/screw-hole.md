# screw_hole(spec, through_depth)

Full parametric screw hole with clearance/tap options. Extends `SteppedBore` with additional hole kinds and FDM teardrop support. Call `.cut()` inside a `BuildPart` context to subtract the hole.

```python
from agentcad.features import screw_hole

sh = screw_hole("M3_cap", through_depth=10, kind="clearance", head="counterbore", builder=b, feature_id="hole_0")
sh.cut()
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `spec` | str or Screw | required | Screw spec like "M3" or "M4_cap" |
| `center` | tuple[float, float] | (0, 0) | XY center of the hole |
| `through_depth` | float | required | Total hole depth (mm) |
| `kind` | str | "clearance" | "clearance" (free-fit hole), "tap" (tap-sized hole), "self_tap" (undersized for self-tapping) |
| `head` | str | "counterbore" | "counterbore", "countersink", or "plain" (no head recess) |
| `fit` | str | "normal" | "tight", "normal", or "loose" — scales through-hole diameter |
| `teardrop_angle` | float | 0 | If > 0, cuts the through-hole as a teardrop for FDM printability |
| `builder` | ContractBuilder | None | Register checks |
| `feature_id` | str | "screw_hole" | Feature/check ID prefix |

## Auto-generated Checks

| Check ID | Type | When |
|---|---|---|
| `{id}_through` | `inner_diameter_at_z` | always |
| `{id}_recess` | `inner_diameter_at_z` | head != "plain" and screw has head |

## Usage

```python
from build123d import BuildPart
from agentcad.features import ContractBuilder, screw_hole

b = ContractBuilder()
with BuildPart() as bp:
    # ... build your part ...
    sh = screw_hole("M3_cap", center=(30, 20), through_depth=10,
                     kind="clearance", head="counterbore", builder=b, feature_id="hole_0")
    sh.cut()
result = bp.part
```

For FDM-printable horizontal holes, set `teardrop_angle=45` to cut the through-hole as a teardrop instead of a plain cylinder.