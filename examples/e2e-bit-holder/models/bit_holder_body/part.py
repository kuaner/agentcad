"""Cylindrical driver-bit holder body.

Coordinate frame:
- +X/+Y are the circular holder footprint
- +Z is vertical, with the closed base at Z=0

The body is a solid cylinder with 20 blind vertical bit slots and a reduced
top neck for a stepped slip-on lid.
"""
import json
import math
from pathlib import Path

from build123d import *


PARAMS = json.loads((Path(__file__).with_name("params.json")).read_text(encoding="utf-8"))

bit_diameter = float(PARAMS["bit_diameter"])
bit_height = float(PARAMS["bit_height"])
slot_diameter = float(PARAMS["slot_diameter"])
slot_radius = slot_diameter / 2
slot_depth = float(PARAMS["slot_depth"])
slot_count = int(PARAMS["slot_count"])
inner_ring_count = int(PARAMS["inner_ring_count"])
outer_ring_count = int(PARAMS["outer_ring_count"])
inner_ring_radius = float(PARAMS["inner_ring_radius"])
outer_ring_radius = float(PARAMS["outer_ring_radius"])
outer_ring_angle_offset = math.radians(float(PARAMS["outer_ring_angle_offset_deg"]))
body_radius = float(PARAMS["body_radius"])
body_height = float(PARAMS["body_height"])
base_thickness = float(PARAMS["base_thickness"])
neck_radius = float(PARAMS["neck_radius"])
neck_height = float(PARAMS["neck_height"])
lid_fit_clearance_diameter = float(PARAMS["lid_fit_clearance_diameter"])

main_height = body_height - neck_height
slot_bottom_z = body_height - slot_depth


def ring_positions(count: int, radius: float, offset: float = 0.0) -> list[tuple[float, float]]:
    return [
        (
            radius * math.cos(offset + 2 * math.pi * i / count),
            radius * math.sin(offset + 2 * math.pi * i / count),
        )
        for i in range(count)
    ]


slot_positions = (
    [(0.0, 0.0)]
    + ring_positions(inner_ring_count, inner_ring_radius)
    + ring_positions(outer_ring_count, outer_ring_radius, outer_ring_angle_offset)
)


def build():
    if len(slot_positions) != slot_count:
        raise ValueError("slot_count does not match generated slot positions")
    if slot_bottom_z < base_thickness - 0.01:
        raise ValueError("slot_depth violates requested base thickness")

    with BuildPart() as body:
        Cylinder(
            radius=body_radius,
            height=main_height,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )
        with Locations((0, 0, main_height)):
            Cylinder(
                radius=neck_radius,
                height=neck_height,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )

        for x, y in slot_positions:
            with Locations((x, y, slot_bottom_z - 0.2)):
                Cylinder(
                    radius=slot_radius,
                    height=slot_depth + 0.4,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                    mode=Mode.SUBTRACT,
                )

    return body.part


result = build()

metadata = {
    "schema": "agentcad.part.metadata.v1",
    "units": "mm",
    "model": "bit_holder_body",
    "bit": {
        "diameter_mm": bit_diameter,
        "height_mm": bit_height,
    },
    "slots": {
        "count": slot_count,
        "diameter_mm": slot_diameter,
        "depth_mm": slot_depth,
        "base_thickness_mm": base_thickness,
        "positions_mm": [[round(x, 3), round(y, 3), body_height] for x, y in slot_positions],
        "layout": {
            "center": 1,
            "inner_ring": inner_ring_count,
            "outer_ring": outer_ring_count,
            "inner_ring_radius_mm": inner_ring_radius,
            "outer_ring_radius_mm": outer_ring_radius,
        },
    },
    "lid_interface": {
        "body_outer_diameter_mm": body_radius * 2,
        "neck_outer_diameter_mm": neck_radius * 2,
        "neck_height_mm": neck_height,
        "recommended_lid_inner_diameter_mm": neck_radius * 2 + lid_fit_clearance_diameter,
    },
    "bbox_expected_mm": [body_radius * 2, body_radius * 2, body_height],
}
