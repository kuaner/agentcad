"""Cylindrical driver-bit holder body with screw-lid interface.

Coordinate frame:
- +X/+Y are the circular holder footprint
- +Z is vertical, with the closed base at Z=0

The body is a solid cylinder with 20 blind vertical bit slots and an
external sinusoidal 3-start thread at the top for a screw-on lid.
The outer surface below the thread zone has a diamond knurl pattern.
"""
import json
import math
from pathlib import Path

from build123d import *
from agentcad.features.thread import sinusoidal_thread
from agentcad.features.knurl import helical_knurl


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

thread_pitch = float(PARAMS["thread_pitch"])
thread_amplitude = float(PARAMS["thread_amplitude"])
thread_tooth_height = float(PARAMS["thread_tooth_height"])
thread_starts = int(PARAMS["thread_starts"])
thread_engagement_height = float(PARAMS["thread_engagement_height"])
thread_radius = float(PARAMS["thread_radius"])
thread_clearance_diameter = float(PARAMS["thread_clearance_diameter"])

knurl_enabled = bool(PARAMS.get("knurl_enabled", False))
knurl_angle = float(PARAMS.get("knurl_angle", 35.0))
knurl_depth = float(PARAMS.get("knurl_depth", 0.4))
knurl_width = float(PARAMS.get("knurl_width", 1.5))
knurl_density = float(PARAMS.get("knurl_density", 0.8))

slot_bottom_z = body_height - slot_depth
thread_zone_start = body_height - thread_engagement_height
knurl_zone_height = thread_zone_start - 2.0


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
        # Main cylinder (below thread zone)
        Cylinder(
            radius=body_radius,
            height=thread_zone_start,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )

        # Thread zone: reduced diameter for thread engagement
        with Locations((0, 0, thread_zone_start)):
            Cylinder(
                radius=thread_radius,
                height=thread_engagement_height,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )

        # Bit slots
        for x, y in slot_positions:
            with Locations((x, y, slot_bottom_z - 0.2)):
                Cylinder(
                    radius=slot_radius,
                    height=slot_depth + 0.4,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                    mode=Mode.SUBTRACT,
                )

        # External thread at top
        thread = sinusoidal_thread(
            radius=thread_radius,
            pitch=thread_pitch,
            height=thread_engagement_height,
            amplitude=thread_amplitude,
            tooth_height=thread_tooth_height,
            n_starts=thread_starts,
        )
        add(thread.moved(Location((0, 0, thread_zone_start))))

        # Diamond knurl on outer surface below thread zone
        if knurl_enabled and knurl_zone_height > 0:
            for groove in helical_knurl(
                radius=body_radius,
                height=knurl_zone_height,
                angle=knurl_angle,
                depth=knurl_depth,
                width=knurl_width,
                density=knurl_density,
            ):
                add(groove.moved(Location((0, 0, 1.0))), mode=Mode.SUBTRACT)

    return body.part


result = build()

thread_outer_diameter = (thread_radius + thread_amplitude) * 2

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
        "type": "screw_thread",
        "thread_pitch_mm": thread_pitch,
        "thread_starts": thread_starts,
        "thread_engagement_height_mm": thread_engagement_height,
        "thread_radius_mm": thread_radius,
        "thread_outer_diameter_mm": round(thread_outer_diameter, 3),
        "thread_clearance_diameter_mm": thread_clearance_diameter,
        "recommended_lid_inner_radius_mm": round(thread_radius + thread_clearance_diameter / 2, 3),
    },
    "interfaces": {
        "lid_neck": {
            "axis": {"point": [0, 0, thread_zone_start], "direction": [0, 0, 1]},
            "outer_cylinder": {
                "type": "cylinder",
                "axis": "z",
                "center": [0, 0],
                "radius_mm": thread_radius,
                "z_range": [round(thread_zone_start, 3), round(body_height, 3)],
                "surface": "outer",
                "tolerance_mm": thread_amplitude + 0.5,
            },
        }
    },
    "bbox_expected_mm": [body_radius * 2, body_radius * 2, body_height],
}
