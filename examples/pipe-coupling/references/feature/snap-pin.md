# snap_pin / snap_pin_socket

Double-ended snap-fit pin and matching socket for press-fit connections.

```python
from agentcad.features import snap_pin, snap_pin_socket

pin = snap_pin("standard", builder=b, feature_id="pin")
socket = snap_pin_socket("standard", builder=b, feature_id="pin_socket")
```

## Predefined Sizes

| Size | Diameter | Length | Snap | Nub depth | Thickness |
|---|---|---|---|---|---|
| "tiny" | 2.5 mm | 4.0 mm | 0.25 mm | 0.9 mm | 0.8 mm |
| "small" | 3.2 mm | 6.0 mm | 0.4 mm | 1.2 mm | 1.0 mm |
| "medium" | 4.6 mm | 8.0 mm | 0.45 mm | 1.5 mm | 1.4 mm |
| "standard" | 7.0 mm | 10.8 mm | 0.5 mm | 1.8 mm | 1.8 mm |

Any parameter can be overridden by passing the keyword argument.

## snap_pin Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `size` | str | "standard" | Predefined size: "tiny", "small", "medium", "standard" |
| `diameter` | float | None | Override pin outer diameter (mm) |
| `length` | float | None | Override pin total length (mm) |
| `snap` | float | None | Override nub projection depth (mm) |
| `nub_depth` | float | None | Override nub distance from pin end (mm) |
| `thickness` | float | None | Override wall thickness (mm) |
| `clearance` | float | 0.2 | Shrink pin from socket walls (mm) |
| `pointed` | bool | True | Pointed tip (True) or rounded tip (False) |
| `center` | tuple[float, float] | (0, 0) | XY center position |
| `base_z` | float | 0 | Z position of the base |
| `builder` | ContractBuilder | None | Register checks |
| `feature_id` | str | "snap_pin" | Feature/check ID prefix |

## snap_pin_socket Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `size` | str | "standard" | Same predefined sizes as snap_pin |
| `diameter` | float | None | Override socket diameter (mm) |
| `length` | float | None | Override socket length (mm) |
| `snap` | float | None | Override nub groove width (mm) |
| `nub_depth` | float | None | Override nub groove depth position (mm) |
| `thickness` | float | None | Override wall thickness (mm) |
| `fixed` | bool | True | Flat-sided socket (anti-rotation) or round |
| `clearance` | float | 0.2 | Socket wall clearance from pin (mm) |
| `pointed` | bool | True | Match pin tip shape |
| `center` | tuple[float, float] | (0, 0) | XY center position |
| `base_z` | float | 0 | Z position of the base |
| `builder` | ContractBuilder | None | Register checks |
| `feature_id` | str | "snap_pin_socket" | Feature/check ID prefix |

## Auto-generated Checks

**snap_pin:**

| Check ID | Type | When |
|---|---|---|
| `{id}_bbox` | `bbox_size` | always |
| `{id}_shaft_od` | `outer_diameter_at_z` | always |

**snap_pin_socket:**

| Check ID | Type | When |
|---|---|---|
| `{id}_bbox` | `bbox_size` | always |
| `{id}_id` | `inner_diameter_at_z` | always |

## Usage

```python
from build123d import BuildPart, add, subtract
from agentcad.features import ContractBuilder, snap_pin, snap_pin_socket

b = ContractBuilder()
with BuildPart() as bp:
    # Add the pin as a positive solid
    pin = snap_pin("medium", builder=b, feature_id="pin")
    add(pin)

    # Subtract the socket into a host part
    socket = snap_pin_socket("medium", builder=b, feature_id="pin_socket")
    subtract(socket)

result = bp.part
```

The pin has locking nubs at both ends that flex inward when pressed into the socket, then lock when the nubs reach the groove. The socket is a subtractive mask — use `subtract()` to cut it into your host part.

`fixed=True` produces a D-shaped socket (flat sides prevent pin rotation). `fixed=False` produces a round socket that allows free rotation.