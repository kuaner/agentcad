"""8025 fan to 80mm duct adapter — rewritten with feature helpers.

Uses agentcad.features (duct_socket, mounting_pattern) and agentcad.hardware
for screw specs. The ContractBuilder auto-generates feature + check entries.
"""
import json
from pathlib import Path

from build123d import (
    Align,
    BuildPart,
    BuildSketch,
    Cone,
    Cylinder,
    Locations,
    Mode,
    Plane,
    RectangleRounded,
    add,
    extrude,
)

from agentcad.features import ContractBuilder, duct_socket, mounting_pattern
from agentcad.hardware import screw

PARAMS = json.loads(Path(__file__).with_name("params.json").read_text(encoding="utf-8"))

flange_size = float(PARAMS["flange_size"])
flange_thickness = float(PARAMS["flange_thickness"])
flange_corner_radius = float(PARAMS["flange_corner_radius"])
mount_spacing = float(PARAMS["fan_mount_spacing"])
fan_air_opening = float(PARAMS["fan_air_opening_diameter"])
socket_od = float(PARAMS["duct_socket_outer_diameter"])
socket_length = float(PARAMS["duct_socket_length"])
duct_wall = float(PARAMS["duct_wall_thickness"])
lead_in = float(PARAMS["lead_in_chamfer"])
duct_id = float(PARAMS["duct_inner_diameter"])

socket_id = socket_od - 2 * duct_wall
air_bore = min(fan_air_opening, socket_id)
total_height = flange_thickness + socket_length
half = mount_spacing / 2

m4 = screw("M4")
head_recess_depth = 1.8


def build():
    b = ContractBuilder(
        intent="8025 fan to 80mm duct adapter (feature helpers)",
    )

    with BuildPart() as adapter:
        # --- Flange ---
        with BuildSketch(Plane.XY) as sk:
            RectangleRounded(flange_size, flange_size, flange_corner_radius)
        extrude(amount=flange_thickness)
        b.add_feature({
            "id": "square_fan_flange",
            "description": f"rounded flange {flange_size}x{flange_size}x{flange_thickness}mm",
        })
        b.add_check({"id": "overall_bbox", "type": "bbox_size",
                      "expected": [flange_size, flange_size, total_height],
                      "tolerance": 0.6, "feature_ref": "square_fan_flange"})
        b.add_check({"id": "watertight_body", "type": "watertight",
                      "expected": True, "feature_ref": "square_fan_flange"})

        # --- Duct socket (feature helper) ---
        sock = duct_socket(
            outer_diameter=socket_od,
            inner_diameter=air_bore,
            length=socket_length - lead_in,
            base_z=flange_thickness,
            builder=b,
            feature_id="round_duct_socket",
        )
        add(sock)

        # Outer diameter checks (duct_socket only checks inner diameter)
        b.add_check({"id": "socket_od_base", "type": "outer_diameter_at_z",
                      "z": 6.0, "expected": socket_od, "tolerance": 0.3,
                      "feature_ref": "round_duct_socket"})
        b.add_check({"id": "socket_od_tip_start", "type": "outer_diameter_at_z",
                      "z": total_height - lead_in, "expected": socket_od, "tolerance": 0.35,
                      "feature_ref": "round_duct_socket"})

        # --- Lead-in cone ---
        with Locations((0, 0, total_height - lead_in)):
            Cone(bottom_radius=socket_od / 2,
                 top_radius=(socket_od - 2 * lead_in) / 2,
                 height=lead_in, align=(Align.CENTER, Align.CENTER, Align.MIN))
        b.add_feature({
            "id": "duct_lead_in", "description": f"lead-in chamfer {lead_in}mm",
        })
        b.add_check({"id": "lead_in_dia_decreases", "type": "diameter_decreases_along_z",
                      "z_values": [total_height - lead_in, total_height - lead_in / 2, total_height],
                      "epsilon": 0.05, "feature_ref": "duct_lead_in"})

        # --- Air bore (through flange + lead-in; socket already bored by duct_socket) ---
        with Locations((0, 0, -0.5)):
            Cylinder(radius=air_bore / 2, height=total_height + 1.0,
                     align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)

        # --- Mounting holes (feature helper) ---
        holes = mounting_pattern(
            m4, kind="square", spacing=mount_spacing,
            depth=flange_thickness, builder=b, feature_id="fan_mounting_holes",
        )
        add(holes, mode=Mode.SUBTRACT)

        # --- Screw head recesses ---
        for x, y in [(-half, -half), (half, -half), (-half, half), (half, half)]:
            with Locations((x, y, flange_thickness - head_recess_depth)):
                Cylinder(radius=m4.head_diameter / 2, height=head_recess_depth + 0.1,
                         align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)

    # Deliverable checks
    b.add_feature({"id": "deliverable_artifacts", "description": "STEP and STL exports"})
    b.add_check({"id": "step_artifact", "type": "artifact_exists",
                  "path": "outputs/fan_duct_adapter_v2.step",
                  "feature_ref": "deliverable_artifacts"})
    b.add_check({"id": "stl_artifact", "type": "artifact_exists",
                  "path": "outputs/fan_duct_adapter_v2.stl",
                  "feature_ref": "deliverable_artifacts"})

    project = Path(__file__).resolve().parents[2]
    b.write_to(project, "fan_duct_adapter_v2")

    return adapter.part, b


result, builder = build()

metadata = {
    "schema": "agentcad.part.metadata.v1",
    "units": "mm",
    "model": "fan_duct_adapter_v2",
    "mounting": {
        "hole_count": 4,
        "pattern_spacing_mm": mount_spacing,
        "screw_spec": m4.name,
        "screw_clearance_diameter_mm": m4.through_hole_diameter("normal"),
    },
    "duct": {
        "inner_diameter_mm": duct_id,
        "socket_outer_diameter_mm": socket_od,
        "socket_inner_diameter_mm": socket_id,
        "socket_length_mm": socket_length,
    },
    "bbox_expected_mm": [flange_size, flange_size, total_height],
}
