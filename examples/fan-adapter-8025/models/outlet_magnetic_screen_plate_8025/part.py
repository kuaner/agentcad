"""8025 outlet magnetic screen adapter plate.

Coordinate frame:
- +X right across fan frame
- +Y back across fan frame
- +Z from fan side toward the window screen

The fan-side face is Z=0. The screen-facing / service face is
Z=plate_thickness. Screws are installed from the screen-facing side into the
fan. After the screws are installed, magnets can be glued into the larger top
pockets.

Four corner features reuse the same XY positions as the fan screws:
- through screw clearance hole to the fan
- screen-side screw head recess below the magnet pocket
- screen-side 12 mm magnet pocket for glued magnets
"""
import json
from pathlib import Path

from build123d import *


PARAMS = json.loads((Path(__file__).with_name("params.json")).read_text(encoding="utf-8"))

fan_frame_size = float(PARAMS["fan_frame_size"])
mount_spacing = float(PARAMS["fan_mount_spacing"])
plate_size = float(PARAMS["plate_size"])
plate_thickness = float(PARAMS["plate_thickness"])
corner_radius = float(PARAMS["corner_radius"])
air_opening_dia = float(PARAMS["air_opening_diameter"])
screw_dia = float(PARAMS["screw_clearance_diameter"])
screw_head_dia = float(PARAMS["screw_head_recess_diameter"])
screw_head_recess_depth = float(PARAMS["screw_head_recess_depth"])
magnet_pocket_dia = float(PARAMS["magnet_pocket_diameter"])
magnet_nominal_dia = float(PARAMS["magnet_nominal_diameter"])
magnet_pocket_depth = float(PARAMS["magnet_pocket_depth"])
magnet_nominal_thickness = float(PARAMS["magnet_nominal_thickness"])
magnet_glue_clearance = float(PARAMS["magnet_glue_clearance"])
edge_chamfer = float(PARAMS["edge_chamfer"])

half_spacing = mount_spacing / 2
corner_positions = [
    (-half_spacing, -half_spacing),
    (half_spacing, -half_spacing),
    (-half_spacing, half_spacing),
    (half_spacing, half_spacing),
]


def build():
    with BuildPart() as plate:
        with BuildSketch(Plane.XY) as plate_profile:
            RectangleRounded(plate_size, plate_size, corner_radius)
        extrude(amount=plate_thickness)

        # Main exhaust opening through the plate.
        with Locations((0, 0, -0.5)):
            Cylinder(
                radius=air_opening_dia / 2,
                height=plate_thickness + 1.0,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT,
            )

        for x, y in corner_positions:
            # Through screw clearance.
            with Locations((x, y, -0.5)):
                Cylinder(
                    radius=screw_dia / 2,
                    height=plate_thickness + 1.0,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                    mode=Mode.SUBTRACT,
                )

            # Screen-side magnet pocket, coaxial with the screw hole. The
            # screw remains installable before the magnet is glued in.
            with Locations((x, y, plate_thickness - magnet_pocket_depth)):
                Cylinder(
                    radius=magnet_pocket_dia / 2,
                    height=magnet_pocket_depth + 0.05,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                    mode=Mode.SUBTRACT,
                )

            # Screen-side screw head recess below the magnet pocket. This
            # creates a three-step bore: screw clearance -> head recess ->
            # larger magnet glue pocket, all opened from the accessible side.
            screw_recess_z = plate_thickness - magnet_pocket_depth - screw_head_recess_depth
            with Locations((x, y, screw_recess_z)):
                Cylinder(
                    radius=screw_head_dia / 2,
                    height=screw_head_recess_depth + 0.05,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                    mode=Mode.SUBTRACT,
                )

        # Light front/back edge break for handling and print friendliness.
        try:
            edges = plate.edges().filter_by(Axis.Z)
            fillet(edges, radius=edge_chamfer)
        except Exception:
            pass

    return plate.part


result = build()

metadata = {
    "schema": "agentcad.part.metadata.v1",
    "units": "mm",
    "model": "outlet_magnetic_screen_plate_8025",
    "fan": {
        "frame_size_mm": fan_frame_size,
    },
    "air_opening": {
        "diameter_mm": air_opening_dia,
    },
    "mounting": {
        "hole_count": 4,
        "pattern_spacing_mm": mount_spacing,
        "screw_clearance_diameter_mm": screw_dia,
        "screw_head_recess_diameter_mm": screw_head_dia,
        "screw_head_recess_depth_mm": screw_head_recess_depth,
        "screw_head_recess_side": "screen",
        "screw_install_side": "screen",
        "positions_mm": [[x, y, 0] for x, y in corner_positions],
    },
    "magnets": {
        "pocket_count": 4,
        "nominal_diameter_mm": magnet_nominal_dia,
        "nominal_thickness_mm": magnet_nominal_thickness,
        "pocket_diameter_mm": magnet_pocket_dia,
        "pocket_depth_mm": magnet_pocket_depth,
        "pocket_side": "screen",
        "glue_clearance_mm": magnet_glue_clearance,
        "coaxial_with_mounting_holes": True,
        "positions_mm": [[x, y, plate_thickness] for x, y in corner_positions],
    },
    "bbox_expected_mm": [plate_size, plate_size, plate_thickness],
}
