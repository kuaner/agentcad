# threaded_rod(spec, length)

ISO-standard threaded rod. Returns a positive solid with helical thread profile.

```python
from agentcad.features import threaded_rod

rod = threaded_rod("M3", length=20, builder=b, feature_id="shaft")
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `spec` | str or Screw | required | Screw spec like "M3" — determines diameter and pitch |
| `length` | float | required | Rod length along Z (mm) |
| `n_starts` | int | 1 | Number of thread starts (1 = single, 2+ = multi-start) |
| `builder` | ContractBuilder | None | Register checks |
| `feature_id` | str | "threaded_rod" | Feature/check ID prefix |

## Auto-generated Checks

| Check ID | Type | When |
|---|---|---|
| `{id}_od` | `outer_diameter_at_z` | always |

## Usage

```python
from build123d import BuildPart, add
from agentcad.features import ContractBuilder, threaded_rod

b = ContractBuilder()
with BuildPart() as bp:
    rod = threaded_rod("M3", length=20, builder=b, feature_id="shaft")
    add(rod)
result = bp.part
```

Uses ISO coarse pitch values from the hardware database: M3→0.5mm, M4→0.7mm, M5→0.8mm, M6→1.0mm, M8→1.25mm. Internally wraps `sinusoidal_thread` with the spec-derived pitch.