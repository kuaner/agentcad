"""8025 fan to 80 mm duct adapter.

Coordinate frame:
- +X right across fan frame
- +Y back across fan frame
- +Z from fan face toward the duct

The fan side is the bottom face of the square flange at Z=0. The round male
socket starts on top of the flange and extends along +Z.
"""
import json
from pathlib import Path

from build123d import *


PARAMS = json.loads((Path(__file__).with_name("params.json")).read_text(encoding="utf-8"))

fan_frame_size = float(PARAMS["fan_frame_size"])
fan_depth = float(PARAMS["fan_depth"])
mount_spacing = float(PARAMS["fan_mount_spacing"])
screw_dia = float(PARAMS["fan_screw_clearance_diameter"])
screw_head_dia = float(PARAMS["fan_screw_head_diameter"])
screw_head_recess_depth = float(PARAMS["fan_screw_head_recess_depth"])
flange_size = float(PARAMS["flange_size"])
flange_thickness = float(PARAMS["flange_thickness"])
flange_corner_radius = float(PARAMS["flange_corner_radius"])
fan_air_opening_dia = float(PARAMS["fan_air_opening_diameter"])
duct_inner_dia = float(PARAMS["duct_inner_diameter"])
socket_od = float(PARAMS["duct_socket_outer_diameter"])
socket_length = float(PARAMS["duct_socket_length"])
duct_wall_thickness = float(PARAMS["duct_wall_thickness"])
lead_in_chamfer = float(PARAMS["lead_in_chamfer"])

socket_id = socket_od - 2 * duct_wall_thickness
air_bore_dia = min(fan_air_opening_dia, socket_id)
total_height = flange_thickness + socket_length
half_spacing = mount_spacing / 2
screw_positions = [
    (-half_spacing, -half_spacing),
    (half_spacing, -half_spacing),
    (-half_spacing, half_spacing),
    (half_spacing, half_spacing),
]


def build():
    with BuildPart() as adapter:
        with BuildSketch(Plane.XY) as flange_profile:
            RectangleRounded(flange_size, flange_size, flange_corner_radius)
        extrude(amount=flange_thickness)

        with Locations((0, 0, flange_thickness)):
            Cylinder(
                radius=socket_od / 2,
                height=socket_length - lead_in_chamfer,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )

        # Small lead-in chamfer at the duct insertion end.
        with Locations((0, 0, total_height - lead_in_chamfer)):
            Cone(
                bottom_radius=socket_od / 2,
                top_radius=(socket_od - 2 * lead_in_chamfer) / 2,
                height=lead_in_chamfer,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )

        # Main air path through flange and duct socket.
        with Locations((0, 0, -0.5)):
            Cylinder(
                radius=air_bore_dia / 2,
                height=total_height + 1.0,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT,
            )

        # Four through holes matching the common 80 mm fan 71.5 mm pattern.
        for x, y in screw_positions:
            with Locations((x, y, -0.5)):
                Cylinder(
                    radius=screw_dia / 2,
                    height=flange_thickness + 1.0,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                    mode=Mode.SUBTRACT,
                )

        # Shallow screw head recesses on the duct side of the flange.
        for x, y in screw_positions:
            with Locations((x, y, flange_thickness - screw_head_recess_depth)):
                Cylinder(
                    radius=screw_head_dia / 2,
                    height=screw_head_recess_depth + 0.1,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                    mode=Mode.SUBTRACT,
                )

    return adapter.part


result = build()

metadata = {
    "schema": "agentcad.part.metadata.v1",
    "units": "mm",
    "model": "fan_duct_adapter_8025",
    "fan": {
        "frame_size_mm": fan_frame_size,
        "depth_mm": fan_depth,
        "air_opening_diameter_mm": fan_air_opening_dia,
    },
    "mounting": {
        "hole_count": 4,
        "pattern_spacing_mm": mount_spacing,
        "screw_clearance_diameter_mm": screw_dia,
        "screw_positions_mm": [[x, y, 0] for x, y in screw_positions],
    },
    "duct": {
        "inner_diameter_mm": duct_inner_dia,
        "socket_outer_diameter_mm": socket_od,
        "socket_inner_diameter_mm": socket_id,
        "socket_length_mm": socket_length,
    },
    "bbox_expected_mm": [flange_size, flange_size, total_height],
}
