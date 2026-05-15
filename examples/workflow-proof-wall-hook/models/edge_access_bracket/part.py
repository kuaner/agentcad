"""Workflow proof wall hook.

This model intentionally combines several risks that should be caught by the
standard AgentCAD workflow: edge-adjacent screw holes, tool access, a cantilever
hook root, a retaining lip, and reinforcing ribs.
"""
import json
from pathlib import Path

from build123d import *

PARAMS = json.loads((Path(__file__).with_name("params.json")).read_text(encoding="utf-8"))

base_width = float(PARAMS["base_width"])
base_depth = float(PARAMS["base_depth"])
base_thickness = float(PARAMS["base_thickness"])
hole_spacing = float(PARAMS["hole_spacing"])
hole_y = float(PARAMS["hole_y"])
hole_diameter = float(PARAMS["hole_diameter"])
hook_width = float(PARAMS["hook_width"])
hook_arm_depth = float(PARAMS["hook_arm_depth"])
hook_root_y = float(PARAMS["hook_root_y"])
hook_arm_thickness = float(PARAMS["hook_arm_thickness"])
hook_lip_thickness = float(PARAMS["hook_lip_thickness"])
hook_lip_height = float(PARAMS["hook_lip_height"])
rib_thickness = float(PARAMS["rib_thickness"])
rib_height = float(PARAMS["rib_height"])
rib_depth = float(PARAMS["rib_depth"])

hole_radius = hole_diameter / 2.0
hole_xs = [-hole_spacing / 2.0, hole_spacing / 2.0]
hook_end_y = hook_root_y + hook_arm_depth
lip_center_y = hook_end_y - hook_lip_thickness / 2.0
rib_y_center = hook_root_y + rib_depth / 2.0
rib_xs = [-hook_width / 2.0 + rib_thickness / 2.0, hook_width / 2.0 - rib_thickness / 2.0]


def build():
    with BuildPart() as bp:
        Box(
            base_width,
            base_depth,
            base_thickness,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )

        with Locations((0, hook_root_y + hook_arm_depth / 2.0, base_thickness)):
            Box(
                hook_width,
                hook_arm_depth,
                hook_arm_thickness,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )

        with Locations((0, lip_center_y, base_thickness)):
            Box(
                hook_width,
                hook_lip_thickness,
                hook_lip_height,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )

        for rib_x in rib_xs:
            with Locations((rib_x, rib_y_center, base_thickness)):
                Box(
                    rib_thickness,
                    rib_depth,
                    rib_height,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                )

        for hole_x in hole_xs:
            with Locations((hole_x, hole_y, -0.5)):
                Cylinder(
                    radius=hole_radius,
                    height=base_thickness + 1.0,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                    mode=Mode.SUBTRACT,
                )
    return bp.part


result = build()
metadata = {
    "schema": "agentcad.part.metadata.v1",
    "units": "mm",
    "anchors": {
        "origin": [0, 0, 0],
        "x_min": [-base_width / 2, 0, 0],
        "x_max": [base_width / 2, 0, 0],
    },
    "interfaces": {
        "left_wall_fastener": {
            "kind": "screw_axis",
            "axis": {"point": [hole_xs[0], hole_y, base_thickness / 2.0], "direction": [0.0, 0.0, 1.0]},
            "inner_cylinder": {
                "type": "cylinder",
                "axis": "z",
                "center": [hole_xs[0], hole_y],
                "radius": hole_radius,
                "z_range": [0.0, base_thickness],
            },
        },
        "right_wall_fastener": {
            "kind": "screw_axis",
            "axis": {"point": [hole_xs[1], hole_y, base_thickness / 2.0], "direction": [0.0, 0.0, 1.0]},
            "inner_cylinder": {
                "type": "cylinder",
                "axis": "z",
                "center": [hole_xs[1], hole_y],
                "radius": hole_radius,
                "z_range": [0.0, base_thickness],
            },
        },
    },
}
