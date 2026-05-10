import json
from pathlib import Path

import build123d as b

PARAMS = json.loads((Path(__file__).with_name("params.json")).read_text(encoding="utf-8"))

base_width = float(PARAMS["base_width"])
base_depth = float(PARAMS["base_depth"])
base_thickness = float(PARAMS["base_thickness"])
flange_height = float(PARAMS["flange_height"])
flange_thickness = float(PARAMS["flange_thickness"])
hole_diameter = float(PARAMS["hole_diameter"])
hole_spacing = float(PARAMS["hole_spacing"])


def build():
    with b.BuildPart() as bp:
        # Base plate: X centered, Y centered, Z from 0 to base_thickness
        b.Box(base_width, base_depth, base_thickness, align=(b.Align.CENTER, b.Align.CENTER, b.Align.MIN))
        # Flange: back edge, rising from base top
        with b.Locations((0, base_depth / 2 - flange_thickness / 2, base_thickness)):
            b.Box(base_width, flange_thickness, flange_height)
        # Left hole
        with b.Locations((-hole_spacing / 2, 0, base_thickness / 2)):
            b.Hole(radius=hole_diameter / 2, depth=base_thickness)
        # Right hole
        with b.Locations((hole_spacing / 2, 0, base_thickness / 2)):
            b.Hole(radius=hole_diameter / 2, depth=base_thickness)
    return bp.part


result = build()
metadata = {
    "schema": "agentcad.part.metadata.v1",
    "units": "mm",
    "interfaces": {
        "left_hole": {
            "type": "cylinder",
            "axis": "z",
            "center": [-hole_spacing / 2, 0, base_thickness / 2],
            "radius": hole_diameter / 2,
            "z_range": [0, base_thickness],
        },
        "right_hole": {
            "type": "cylinder",
            "axis": "z",
            "center": [hole_spacing / 2, 0, base_thickness / 2],
            "radius": hole_diameter / 2,
            "z_range": [0, base_thickness],
        },
    },
}
