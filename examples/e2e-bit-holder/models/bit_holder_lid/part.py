"""Screw-on lid for the driver-bit holder body.

Coordinate frame:
- +X/+Y are the circular lid footprint
- +Z is vertical, with the lid opening at Z=0 and top at +Z

The lid has an internal sinusoidal 3-start thread that engages with the
body's external thread. A diamond knurl pattern on the outer surface
provides grip for tightening.
"""
import json
from pathlib import Path

from build123d import *
from agentcad.features.thread import sinusoidal_thread
from agentcad.features.knurl import helical_knurl


PARAMS = json.loads((Path(__file__).with_name("params.json")).read_text(encoding="utf-8"))

body_outer_diameter = float(PARAMS["body_outer_diameter"])
body_thread_radius = float(PARAMS["body_thread_radius"])
body_thread_amplitude = float(PARAMS["body_thread_amplitude"])
thread_pitch = float(PARAMS["thread_pitch"])
thread_tooth_height = float(PARAMS["thread_tooth_height"])
thread_starts = int(PARAMS["thread_starts"])
thread_engagement_height = float(PARAMS["thread_engagement_height"])
thread_clearance_diameter = float(PARAMS["thread_clearance_diameter"])
lid_outer_diameter = float(PARAMS["lid_outer_diameter"])
lid_height = float(PARAMS["lid_height"])
top_thickness = float(PARAMS["top_thickness"])

knurl_enabled = bool(PARAMS.get("knurl_enabled", False))
knurl_angle = float(PARAMS.get("knurl_angle", 35.0))
knurl_depth = float(PARAMS.get("knurl_depth", 0.4))
knurl_width = float(PARAMS.get("knurl_width", 1.5))
knurl_density = float(PARAMS.get("knurl_density", 0.8))

outer_radius = lid_outer_diameter / 2
inner_radius = body_thread_radius + thread_clearance_diameter / 2
recess_depth = lid_height - top_thickness


def build():
    if inner_radius >= outer_radius - 2.0:
        raise ValueError("lid wall too thin for thread")
    if recess_depth > lid_height:
        raise ValueError("recess exceeds lid height")

    with BuildPart() as lid:
        # Outer cylinder
        Cylinder(
            radius=outer_radius,
            height=lid_height,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )

        # Inner recess (void for thread engagement)
        with Locations((0, 0, -0.2)):
            Cylinder(
                radius=inner_radius,
                height=recess_depth + 0.2,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT,
            )

        # Internal thread (subtracted from inner wall)
        thread = sinusoidal_thread(
            radius=inner_radius,
            pitch=thread_pitch,
            height=thread_engagement_height,
            amplitude=body_thread_amplitude,
            tooth_height=thread_tooth_height,
            n_starts=thread_starts,
        )
        add(thread, mode=Mode.SUBTRACT)

        # Diamond knurl on outer surface
        if knurl_enabled and lid_height > 5:
            knurl_height = lid_height - top_thickness - 2.0
            if knurl_height > 0:
                for groove in helical_knurl(
                    radius=outer_radius,
                    height=knurl_height,
                    angle=knurl_angle,
                    depth=knurl_depth,
                    width=knurl_width,
                    density=knurl_density,
                ):
                    add(groove.moved(Location((0, 0, 1.0))), mode=Mode.SUBTRACT)

    return lid.part


result = build()

metadata = {
    "schema": "agentcad.part.metadata.v1",
    "units": "mm",
    "model": "bit_holder_lid",
    "fit": {
        "type": "screw_thread",
        "body_outer_diameter_mm": body_outer_diameter,
        "thread_pitch_mm": thread_pitch,
        "thread_starts": thread_starts,
        "thread_inner_radius_mm": round(inner_radius, 3),
        "thread_engagement_height_mm": thread_engagement_height,
        "diametral_clearance_mm": thread_clearance_diameter,
        "radial_clearance_mm": round(thread_clearance_diameter / 2, 3),
    },
    "lid": {
        "outer_diameter_mm": lid_outer_diameter,
        "height_mm": lid_height,
        "top_thickness_mm": top_thickness,
        "recess_depth_mm": recess_depth,
        "skirt_wall_mm": round(outer_radius - inner_radius, 3),
    },
    "interfaces": {
        "recess": {
            "axis": {"point": [0, 0, 0], "direction": [0, 0, 1]},
            "inner_cylinder": {
                "type": "cylinder",
                "axis": "z",
                "center": [0, 0],
                "radius_mm": round(inner_radius, 3),
                "z_range": [0, round(recess_depth, 3)],
                "surface": "inner",
                "tolerance_mm": thread_clearance_diameter / 2,
            },
        }
    },
    "bbox_expected_mm": [lid_outer_diameter, lid_outer_diameter, lid_height],
}
