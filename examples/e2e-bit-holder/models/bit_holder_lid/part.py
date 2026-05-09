"""Stepped slip-on lid for the driver-bit holder body.

Coordinate frame:
- +X/+Y are the circular lid footprint
- +Z is vertical, with the lid opening at Z=0 and top at +Z

The lower recess slips over the body's reduced neck. The recess shoulder and
body shoulder create a simple stepped stop.
"""
import json
from pathlib import Path

from build123d import *


PARAMS = json.loads((Path(__file__).with_name("params.json")).read_text(encoding="utf-8"))

body_outer_diameter = float(PARAMS["body_outer_diameter"])
body_neck_diameter = float(PARAMS["body_neck_diameter"])
body_neck_height = float(PARAMS["body_neck_height"])
fit_clearance_diameter = float(PARAMS["fit_clearance_diameter"])
lid_outer_diameter = float(PARAMS["lid_outer_diameter"])
lid_height = float(PARAMS["lid_height"])
recess_depth = float(PARAMS["recess_depth"])
bottom_chamfer = float(PARAMS["bottom_chamfer"])

inner_diameter = body_neck_diameter + fit_clearance_diameter
inner_radius = inner_diameter / 2
outer_radius = lid_outer_diameter / 2
top_thickness = lid_height - recess_depth


def build():
    if inner_diameter <= body_neck_diameter:
        raise ValueError("lid inner diameter must clear body neck")
    if recess_depth <= body_neck_height:
        raise ValueError("recess depth must exceed body neck height")
    if outer_radius - inner_radius < 2.0:
        raise ValueError("lid skirt is too thin")

    with BuildPart() as lid:
        Cylinder(
            radius=outer_radius,
            height=lid_height,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )

        with Locations((0, 0, -0.2)):
            Cylinder(
                radius=inner_radius,
                height=recess_depth + 0.2,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT,
            )

        # A small lead-in chamfer reduces first-layer elephant-foot friction.
        with Locations((0, 0, -0.1)):
            Cone(
                bottom_radius=inner_radius + bottom_chamfer,
                top_radius=inner_radius,
                height=bottom_chamfer + 0.1,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT,
            )

    return lid.part


result = build()

metadata = {
    "schema": "agentcad.part.metadata.v1",
    "units": "mm",
    "model": "bit_holder_lid",
    "fit": {
        "body_outer_diameter_mm": body_outer_diameter,
        "body_neck_diameter_mm": body_neck_diameter,
        "body_neck_height_mm": body_neck_height,
        "inner_diameter_mm": round(inner_diameter, 3),
        "diametral_clearance_mm": round(fit_clearance_diameter, 3),
        "radial_clearance_mm": round(fit_clearance_diameter / 2, 3),
        "recess_depth_mm": recess_depth,
        "top_clearance_mm": round(recess_depth - body_neck_height, 3),
    },
    "lid": {
        "outer_diameter_mm": lid_outer_diameter,
        "height_mm": lid_height,
        "top_thickness_mm": top_thickness,
        "skirt_wall_mm": outer_radius - inner_radius,
    },
    "bbox_expected_mm": [lid_outer_diameter, lid_outer_diameter, lid_height],
}
