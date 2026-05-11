"""Mounting pillar — feature helper demo.

Validates plate(), boss(), stepped_bore(), and slot() helpers.
A rectangular base plate with a raised boss (with bore) in the center,
four counterbored M4 mounting holes at the corners, and two cable slots.
"""
import json
from pathlib import Path

from build123d import (
    BuildPart,
    Cylinder,
    Location,
    Mode,
    add,
)

from agentcad.features import (
    ContractBuilder,
    boss,
    plate,
    slot,
    stepped_bore,
)
from agentcad.hardware import screw

PARAMS = json.loads(Path(__file__).with_name("params.json").read_text(encoding="utf-8"))

plate_w = float(PARAMS["plate_width"])
plate_d = float(PARAMS["plate_depth"])
plate_t = float(PARAMS["plate_thickness"])
boss_dia = float(PARAMS["boss_diameter"])
boss_h = float(PARAMS["boss_height"])
boss_bore = float(PARAMS["boss_bore_diameter"])
screw_spec = PARAMS["screw_spec"]
spacing_x = float(PARAMS["hole_spacing_x"])
spacing_y = float(PARAMS["hole_spacing_y"])
slot_w = float(PARAMS["slot_width"])
slot_depth = float(PARAMS["slot_depth"])
slot_length = float(PARAMS["slot_length"])
slot_from_edge = float(PARAMS["slot_from_edge"])

s = screw(screw_spec)
total_height = plate_t + boss_h
half_x = spacing_x / 2
half_y = spacing_y / 2
corner_positions = [
    (-half_x, -half_y),
    (half_x, -half_y),
    (-half_x, half_y),
    (half_x, half_y),
]


def build():
    b = ContractBuilder(
        intent="Mounting pillar: plate + boss + stepped_bore + slot",
    )

    with BuildPart() as bp:
        # --- Base plate (feature helper — geometry only, composite model) ---
        plank = plate(plate_w, plate_d, plate_t)
        add(plank)
        b.add_feature({
            "id": "base_plate",
            "description": f"base plate {plate_w}x{plate_d}x{plate_t}mm",
        })

        # --- Central boss with bore (feature helper) ---
        pillar = boss(
            boss_dia, boss_h,
            center=(0, 0), base_z=plate_t,
            inner_diameter=boss_bore,
            builder=b, feature_id="center_boss",
        )
        add(pillar)

        # Boss bore extends through plate
        with BuildPart(mode=Mode.PRIVATE) as bore_ext:
            Cylinder(radius=boss_bore / 2, height=plate_t + 0.5)
        add(bore_ext.part.moved(Location((0, 0, -0.25))), mode=Mode.SUBTRACT)

        # --- Counterbored mounting holes (feature helper) ---
        for i, (cx, cy) in enumerate(corner_positions):
            bore_neg = stepped_bore(
                s, center=(cx, cy),
                through_depth=plate_t,
                bore_kind="counterbore",
                builder=b, feature_id=f"mount_hole_{i}",
            )
            add(bore_neg, mode=Mode.SUBTRACT)

        # --- Cable routing slots (feature helper) ---
        for sign, fid in [(-1, "left_slot"), (1, "right_slot")]:
            cy = sign * (plate_d / 2 - slot_from_edge)
            s_neg = slot(
                slot_w, slot_depth, slot_length,
                center=(0, cy), base_z=plate_t - slot_depth,
                direction="x",
                builder=b, feature_id=fid,
            )
            add(s_neg, mode=Mode.SUBTRACT)

    # --- Overall checks ---
    b.add_check({"id": "overall_bbox", "type": "bbox_size",
                  "expected": [plate_w, plate_d, total_height],
                  "tolerance": 0.6, "feature_ref": "base_plate"})
    b.add_check({"id": "watertight", "type": "watertight",
                  "expected": True, "feature_ref": "base_plate"})

    # --- Deliverables ---
    b.add_feature({"id": "deliverable_artifacts", "description": "STEP and STL exports"})
    b.add_check({"id": "step_artifact", "type": "artifact_exists",
                  "path": "outputs/mounting_pillar.step",
                  "feature_ref": "deliverable_artifacts"})
    b.add_check({"id": "stl_artifact", "type": "artifact_exists",
                  "path": "outputs/mounting_pillar.stl",
                  "feature_ref": "deliverable_artifacts"})

    project = Path(__file__).resolve().parents[2]
    b.write_to(project, "mounting_pillar")

    return bp.part, b


result, builder = build()

metadata = {
    "schema": "agentcad.part.metadata.v1",
    "units": "mm",
    "model": "mounting_pillar",
    "features_used": ["plate", "boss", "stepped_bore", "slot"],
    "screw_spec": s.name,
    "bbox_expected_mm": [plate_w, plate_d, total_height],
}
