# living_hinge_mask(length, thickness)

FDM-printable flex hinge mask. Returns a positive solid — subtract it from your part to create a thin flexible bridge that bends without breaking.

```python
from agentcad.features import living_hinge_mask

lh = living_hinge_mask(length=30, thickness=3, builder=b, feature_id="hinge")
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `length` | float | required | Hinge length along X (mm) |
| `thickness` | float | required | Material thickness the hinge cuts through (mm) |
| `layerheight` | float | 0.2 | Expected FDM layer height; remaining hinge material is 2×layerheight |
| `foldangle` | float | 90 | Interior fold angle in degrees — controls taper width |
| `center` | tuple[float, float] | (0, 0) | XY center position |
| `base_z` | float | 0 | Z position of the mask base |
| `builder` | ContractBuilder | None | Register checks |
| `feature_id` | str | "living_hinge" | Feature/check ID prefix |

## Auto-generated Checks

| Check ID | Type | When |
|---|---|---|
| `{id}_section` | `section_bbox_at_z` | always |

## Usage

```python
from build123d import BuildPart, add, Location, Mode
from agentcad.features import ContractBuilder, living_hinge_mask

b = ContractBuilder()
with BuildPart() as bp:
    # ... build your part ...
    lh = living_hinge_mask(30, 3, layerheight=0.2, foldangle=90, builder=b, feature_id="hinge")
    add(lh, mode=Mode.SUBTRACT)
result = bp.part
```

The mask is a trapezoidal shape: narrow at the bottom (2×layerheight), wider at the top (tapers outward based on foldangle). After subtraction, the remaining material at the hinge line is thin enough to flex but thick enough to print.