"""L-shaped mounting bracket — feature helper version.

Uses plate() for the base and mounting_pattern() for the two M5 holes.
"""
import json
from pathlib import Path

from build123d import (
    Align,
    Box,
    BuildPart,
    Locations,
    Mode,
    add,
)

from agentcad.features import ContractBuilder, plate, mounting_pattern
from agentcad.hardware import screw

PARAMS = json.loads(Path(__file__).with_name("params.json").read_text(encoding="utf-8"))

base_width = float(PARAMS["base_width"])
base_depth = float(PARAMS["base_depth"])
base_thickness = float(PARAMS["base_thickness"])
flange_height = float(PARAMS["flange_height"])
flange_thickness = float(PARAMS["flange_thickness"])
hole_spacing = float(PARAMS["hole_spacing"])

m5 = screw("M5")


def build():
    b = ContractBuilder(
        intent="L-shaped mounting bracket with two M5 through-holes on the base",
    )

    with BuildPart() as bp:
        # Base plate (feature helper — geometry only; bbox is composite)
        plank = plate(base_width, base_depth, base_thickness)
        add(plank)
        b.add_feature({
            "id": "base_plate",
            "description": f"base plate {base_width}x{base_depth}x{base_thickness}mm",
        })
        b.add_check({"id": "base_bbox", "type": "bbox_size",
                      "expected": [base_width, base_depth, flange_height],
                      "tolerance": 1.0, "feature_ref": "base_plate"})
        b.add_check({"id": "watertight", "type": "watertight",
                      "expected": True, "feature_ref": "base_plate"})

        # Vertical flange: back edge, rising from base top
        with Locations((0, base_depth / 2 - flange_thickness / 2, base_thickness)):
            Box(base_width, flange_thickness, flange_height)
        b.add_feature({
            "id": "vertical_flange",
            "description": f"vertical flange {base_width}x{flange_thickness}x{flange_height}mm",
        })
        b.add_check({"id": "flange_bbox", "type": "bbox_size",
                      "expected": [base_width, base_depth, flange_height],
                      "tolerance": 1.0, "feature_ref": "vertical_flange"})

        # Mounting holes (feature helper — geometry + auto checks)
        holes = mounting_pattern(
            m5, kind="linear", spacing=hole_spacing, count=2,
            depth=base_thickness, builder=b, feature_id="mounting_holes",
        )
        add(holes, mode=Mode.SUBTRACT)

    # Deliverables
    b.add_feature({"id": "deliverable_artifacts", "description": "STEP and STL exports"})
    b.add_check({"id": "step_artifact", "type": "artifact_exists",
                  "path": "outputs/l_bracket.step", "feature_ref": "deliverable_artifacts"})
    b.add_check({"id": "stl_artifact", "type": "artifact_exists",
                  "path": "outputs/l_bracket.stl", "feature_ref": "deliverable_artifacts"})

    project = Path(__file__).resolve().parents[2]
    b.write_to(project, "l_bracket")

    return bp.part, b


result, builder = build()

metadata = {
    "schema": "agentcad.part.metadata.v1",
    "units": "mm",
    "interfaces": {
        "left_hole": {
            "type": "cylinder",
            "axis": "z",
            "center": [-hole_spacing / 2, 0, base_thickness / 2],
            "radius": m5.through_hole_diameter("normal") / 2,
            "z_range": [0, base_thickness],
        },
        "right_hole": {
            "type": "cylinder",
            "axis": "z",
            "center": [hole_spacing / 2, 0, base_thickness / 2],
            "radius": m5.through_hole_diameter("normal") / 2,
            "z_range": [0, base_thickness],
        },
    },
}
