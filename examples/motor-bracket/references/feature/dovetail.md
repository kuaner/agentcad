# dovetail(gender, width, height, slide)

Interlocking dovetail joint. Returns a positive solid (male) or a subtractive mask (female).

```python
from agentcad.features import dovetail

male = dovetail("male", width=10, height=6, slide=20, builder=b, feature_id="dt_male")
female = dovetail("female", width=10, height=6, slide=20, builder=b, feature_id="dt_female")
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `gender` | str | required | "male" (additive) or "female" (subtractive mask) |
| `width` | float | required | Width at the wider (top) end (mm) |
| `height` | float | required | Projection height from base (mm) |
| `slide` | float | required | Sliding distance along Y (mm) |
| `slope` | float | 6 | Flank rise/run ratio (4, 6, or 8 standard) |
| `angle` | float | None | Flank angle in degrees (overrides slope) |
| `taper` | float | 0 | Taper angle along the slide direction (mm) |
| `center` | tuple[float, float] | (0, 0) | XY center position |
| `base_z` | float | 0 | Z position of the base |
| `builder` | ContractBuilder | None | Register checks |
| `feature_id` | str | "dovetail" | Feature/check ID prefix |

## Auto-generated Checks

| Check ID | Type | When |
|---|---|---|
| `{id}_bbox` | `bbox_size` | always |

## Usage

```python
from build123d import BuildPart, add, Mode
from agentcad.features import ContractBuilder, dovetail

b = ContractBuilder()
with BuildPart() as bp:
    # ... build your part ...
    female = dovetail("female", width=10, height=6, slide=20, builder=b, feature_id="socket")
    add(female, mode=Mode.SUBTRACT)
result = bp.part

# Male dovetail (add separately)
male = dovetail("male", width=10, height=6, slide=20)
```

Female sockets include 0.1mm clearance for a snug but not binding fit. Use `angle` instead of `slope` for degree-based flank specification (`slope = 1/tan(angle)`).