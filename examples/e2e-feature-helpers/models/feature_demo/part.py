"""Feature demo: mounting bracket using all new Tier-1 helpers."""
import json
from pathlib import Path

from build123d import (
    BuildPart,
    Location,
    Mode,
    add,
)

from agentcad.features import (
    ContractBuilder,
    chamfer_mask,
    nut_trap,
    prismoid,
    screw_hole,
    teardrop,
    tube,
    wedge,
)

PARAMS = json.loads((Path(__file__).with_name("params.json")).read_text(encoding="utf-8"))

plate_w = float(PARAMS["plate_w"])
plate_d = float(PARAMS["plate_d"])
plate_t = float(PARAMS["plate_t"])

b = ContractBuilder(intent="mounting bracket demo using all new feature helpers")

from agentcad.hardware.screws import screw
m3 = screw("M3_cap")

with BuildPart() as bp:
    # Prismoid base plate (wider at bottom, narrower at top)
    base = prismoid(
        (plate_w, plate_d), (plate_w - 6, plate_d - 6), plate_t,
    )
    add(base)

    # Tube spacer / standoff on top center
    spacer = tube(
        outer_diameter=16, inner_diameter=8, height=12,
        base_z=plate_t,
    )
    add(spacer)

    # Wedge gussets reinforcing the tube to the plate
    # Small triangular ribs at the tube base
    for angle in [0, 90, 180, 270]:
        from build123d import Rot
        gusset = wedge(6, 8, 4, direction="+y")
        rad = 7  # just outside the tube (OD=16, r=8, so 7mm from center)
        gx = rad * __import__("math").cos(__import__("math").radians(angle))
        gy = rad * __import__("math").sin(__import__("math").radians(angle))
        add(gusset.moved(Rot(0, 0, angle)).moved(Location((gx, gy, plate_t))))

    # Screw holes with counterbore
    for i, (cx, cy) in enumerate([(-25, -20), (25, -20), (-25, 20), (25, 20)]):
        sh = screw_hole(
            m3, center=(cx, cy), through_depth=plate_t,
            kind="clearance", head="counterbore",
            builder=b, feature_id=f"screw_{i}",
        )
        sh.cut()

    # Nut trap on bottom for one screw location
    nt = nut_trap("M3", depth=5, orientation="top", center=(0, -20), builder=b, feature_id="nut_trap")
    add(nt, mode=Mode.SUBTRACT)

    # Teardrop FDM-printable horizontal hole (for cable/wire pass-through)
    td = teardrop(diameter=6, height=plate_d - 15, angle=45)
    add(td.moved(Location((0, 0, plate_t / 2))), mode=Mode.SUBTRACT)

    # Chamfer on top edges of the plate
    cm = chamfer_mask(plate_w - 6, edge="z", size=1.0)
    add(cm.moved(Location((0, 0, plate_t))), mode=Mode.SUBTRACT)

    # Register non-cutting features
    b.add(feature={"id": "spacer", "description": "tube OD=16 ID=8 h=12"}, checks=[
        {"id": "spacer_od", "type": "outer_diameter_at_z", "z": plate_t + 8,
         "center": [0, 0], "expected": 16, "tolerance": 0.5, "feature_ref": "spacer"},
        {"id": "spacer_id", "type": "inner_diameter_at_z", "z": plate_t + 8,
         "center": [0, 0], "expected": 8, "tolerance": 0.3, "feature_ref": "spacer"},
    ])
    b.add(feature={"id": "fdm_hole", "description": "teardrop d=6 angle=45"}, checks=[
        {"id": "fdm_hole_id", "type": "inner_diameter_at_z", "z": plate_t / 2,
         "center": [0, 0], "expected": 6, "tolerance": 0.5, "feature_ref": "fdm_hole"},
    ])

result = bp.part

b.write_to(Path(__file__).resolve().parent.parent.parent, "feature_demo")

metadata = {
    "schema": "agentcad.part.metadata.v1",
    "units": "mm",
}