"""FDM-printable wall-mounted cable hook.

Coordinate frame:
- +X right
- +Y back, toward the wall
- +Z up

The back plate spans Y[0, 5]. The hook projects forward in -Y, so it is not a
floating top-plate form.
"""
import json
from pathlib import Path

from build123d import *


PARAMS = json.loads((Path(__file__).with_name("params.json")).read_text(encoding="utf-8"))

plate_w = float(PARAMS["back_plate_width"])
plate_h = float(PARAMS["back_plate_height"])
plate_t = float(PARAMS["back_plate_thickness"])
hole_dia = float(PARAMS["screw_clearance_diameter"])
head_dia = float(PARAMS["screw_head_clearance_diameter"])
head_recess_depth = float(PARAMS["screw_head_recess_depth"])
screw_x_offset = float(PARAMS["screw_x_offset"])
screw_z = float(PARAMS["screw_z"])
hook_w = float(PARAMS["hook_width"])
hook_projection = float(PARAMS["hook_projection"])
hook_overlap = float(PARAMS["hook_plate_overlap"])
hook_t = float(PARAMS["hook_thickness"])
hook_center_z = float(PARAMS["hook_center_z"])
lip_depth = float(PARAMS["lip_depth"])
lip_height = float(PARAMS["lip_height"])
rib_w = float(PARAMS["rib_width"])
rib_spacing = float(PARAMS["rib_spacing"])
rib_length = float(PARAMS["rib_length"])

join_overlap = 0.2
front_face_y = 0.0
back_face_y = plate_t
hook_back_y = front_face_y + hook_overlap
hook_front_y = -hook_projection
hook_center_y = (hook_back_y + hook_front_y) / 2
hook_box_length = hook_back_y - hook_front_y
hook_bottom_z = hook_center_z - hook_t / 2
hook_top_z = hook_center_z + hook_t / 2
lip_center_y = hook_front_y - lip_depth / 2
lip_center_z = hook_bottom_z - join_overlap + (lip_height + join_overlap) / 2
rib_center_y = (-rib_length + hook_overlap) / 2
rib_center_z = (hook_top_z - join_overlap + plate_h + join_overlap) / 2
rib_height = (plate_h + join_overlap) - (hook_top_z - join_overlap)
screw_positions = [(-screw_x_offset, screw_z), (screw_x_offset, screw_z)]


def build():
    with BuildPart() as part:
        # Vertical wall/back plate.
        Box(
            plate_w,
            plate_t,
            plate_h,
            align=(Align.CENTER, Align.MIN, Align.MIN),
        )

        # Forward hook arm.
        with Locations((0, hook_center_y, hook_center_z)):
            Box(hook_w, hook_box_length, hook_t)

        # Upturned front lip.
        with Locations((0, lip_center_y, lip_center_z)):
            Box(hook_w, lip_depth, lip_height + join_overlap)

        # Twin web ribs connecting the hook arm to the back plate.
        for x in (-rib_spacing / 2, rib_spacing / 2):
            with Locations((x, rib_center_y, rib_center_z)):
                Box(rib_w, rib_length + hook_overlap, rib_height)

        # Screw clearance holes through the vertical plate.
        for x, z in screw_positions:
            with Locations((x, plate_t / 2, z)):
                Cylinder(
                    radius=hole_dia / 2,
                    height=plate_t + 0.6,
                    rotation=(90, 0, 0),
                    align=(Align.CENTER, Align.CENTER, Align.CENTER),
                    mode=Mode.SUBTRACT,
                )

        # Larger front relief for screw heads.
        for x, z in screw_positions:
            with Locations((x, head_recess_depth / 2 - 0.1, z)):
                Cylinder(
                    radius=head_dia / 2,
                    height=head_recess_depth + 0.2,
                    rotation=(90, 0, 0),
                    align=(Align.CENTER, Align.CENTER, Align.CENTER),
                    mode=Mode.SUBTRACT,
                )

    return part.part


result = build()

metadata = {
    "schema": "agentcad.part.metadata.v1",
    "units": "mm",
    "model": "wall_cable_hook",
    "concept": "vertical back plate with forward hook arm, front lip, and twin support ribs",
    "mounting": {
        "hole_count": 2,
        "clearance_diameter_mm": hole_dia,
        "hole_axis": "Y",
        "positions_mm": [[x, plate_t / 2, z] for x, z in screw_positions],
    },
    "hook": {
        "arm_width_mm": hook_w,
        "projection_mm": hook_projection,
        "arm_thickness_mm": hook_t,
        "lip_height_mm": lip_height,
        "rib_count": 2,
    },
    "bbox_expected_mm": [plate_w, plate_t + hook_projection + lip_depth, plate_h],
}
