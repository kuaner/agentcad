# Hardware Database

Real ISO/DIN dimensions for screws, nuts, washers, and inserts. Helpers that
accept a `spec` string use this database to compute correct hole sizes.

Data sourced from NopSCADlib (GPL-3.0) empirically verified dimensions.

## Lookup

```python
from agentcad.hardware import screw, nut, washer, insert

s = screw("M3")        # → M3_cap (shorthand defaults to cap)
s = screw("M4_hex")    # → M4 hex head
s = screw("M3_dome")   # → M3 button head

n = nut("M3")          # → M3_nut (hex)
n = nut("M4_thin_square")

w = washer("M3")
w = washer("M3_penny")

i = insert("F1BM3")    # → heat-set brass insert
i = insert("M5x12")    # → threaded (DIN 7965)
```

## Screw Properties

| Property | Description |
|---|---|
| `nominal_diameter` | Thread diameter (mm) |
| `head_style` | cap, pan, cs, cs_cap, hex, grub, dome |
| `head_diameter` | Head OD (mm) |
| `head_height` | Head height (mm) |
| `tap_radius` | Tap hole radius |
| `clearance_radius` | Clearance hole radius |
| `pitch` | ISO coarse pitch (mm) |
| `counterbore_diameter()` | Head recess diameter (+ clearance) |
| `counterbore_depth()` | Head recess depth (+ extra) |
| `through_hole_diameter(fit)` | tight/normal/loose |

## Available Screws

| Head style | Sizes |
|---|---|
| Cap (socket head, ISO 4762) | M2, M2.5, M3, M4, M5, M6, M8 |
| CS cap (countersunk socket, ISO 10642) | M2, M3, M4, M5, M6, M8 |
| Dome (button, ISO 7380) | M2, M2.5, M3, M4, M5, M6, M8 |
| Pan (ISO 7045) | M2.5, M3, M4, M5, M6 |
| Hex (ISO 4014) | M3, M4, M5, M6, M8 |
| Grub / set screw (ISO 4026) | M3, M4, M5, M6 |

## Nuts

| Style | Sizes |
|---|---|
| Hex | M2, M2.5, M3, M4, M5, M6, M8 |
| Thin square (DIN 562) | M3, M4, M5, M6, M8 |
| T-nut (extrusion) | M3, M4, M5, M6 |
| Hammer nut | M3, M4 |
| Wing | M4 |

Key nut property: `trap_depth` — recommended nut trap depth for 3D printing.

## Washers

| Kind | Sizes |
|---|---|
| Standard | M2, M2.5, M3, M3.5, M4, M5, M6, M8 |
| Penny | M3, M4, M5, M6, M8 |
| Spring | M3, M4, M5, M6, M8 |
| Rubber | M3 |

## Inserts

| Kind | Spec names |
|---|---|
| Heat-set (brass) | F1BM2, F1BM2.5, F1BM3, F1BM4 |
| Heat-set (short) | CNCKM2.5, CNCKM3, CNCKM4, CNCKM5 |
| Threaded (DIN 7965) | M3x8, M4x10, M5x12, M6x15, M8x18 |

Key insert property: `hole_diameter` — empirically verified print hole size.
