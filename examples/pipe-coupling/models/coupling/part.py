"""Pipe coupling: duct sockets, tube body, O-ring groove, M4 flange bolts.

Tunable values live in params.json. The final geometry must be assigned to
global variable `result`.
"""
import json
from pathlib import Path

from build123d import (
    Align,
    BuildPart,
    Cylinder,
    Location,
    Locations,
    Mode,
    add,
)

from agentcad.features import (
    duct_socket,
    nut_body,
    nut_trap,
    plate,
    screw,
    screw_hole,
    tube,
)

PARAMS = json.loads(
    (Path(__file__).with_name("params.json")).read_text(encoding="utf-8")
)

# Dimensions
pipe_od = float(PARAMS["pipe_od"])              # 20.0
coupling_od = float(PARAMS["coupling_od"])       # 30.0
coupling_id = float(PARAMS["coupling_id"])       # 18.0
socket_length = float(PARAMS["socket_length"])   # 10.0
total_length = float(PARAMS["total_length"])     # 40.0
flange_size = float(PARAMS["flange_size"])       # 44.0
flange_thickness = float(PARAMS["flange_thickness"])  # 4.0
oring_major_r = float(PARAMS["oring_major_radius"])   # 13.5
oring_minor_r = float(PARAMS["oring_minor_radius"])   # 1.5
oring_z = float(PARAMS["oring_z"])               # 20.0
bolt_spacing_x = float(PARAMS["bolt_spacing_x"]) # 14.0
bolt_spacing_y = float(PARAMS["bolt_spacing_y"]) # 14.0
m4_clearance_d = float(PARAMS["m4_clearance_diameter"])  # 4.4
m4_nut_depth = float(PARAMS["m4_nut_depth"])     # 4.0

# Derived
center_tube_height = total_length - 2 * socket_length  # 20.0
m4_clearance_r = m4_clearance_d / 2  # 2.2
overshoot = 1.0  # overshoot for subtraction cylinders
# O-ring groove dimensions (annular ring approach)
groove_od = coupling_od / 2 + overshoot / 2        # 15.5mm (slightly larger than tube OD)
groove_id = oring_major_r - oring_minor_r           # 12.0mm (groove bottom radius)
groove_height = 2 * oring_minor_r + overshoot       # 4.0mm
groove_z_start = oring_z - oring_minor_r - overshoot / 2  # 18.5mm


def build():
    with BuildPart() as bp:
        # === Positive geometry ===

        # Bottom duct socket (Z=0 to 10): pipe insertion end
        bottom_socket = duct_socket(
            coupling_od, pipe_od, socket_length, base_z=0
        )
        add(bottom_socket)

        # Center tube (Z=10 to 30): connecting body
        center_tube = tube(
            coupling_od, coupling_id, center_tube_height, base_z=socket_length
        )
        add(center_tube)

        # Top duct socket (Z=30 to 40): pipe insertion end
        top_socket = duct_socket(
            coupling_od, pipe_od, socket_length,
            base_z=total_length - socket_length,
        )
        add(top_socket)

        # Bottom flange (Z=0 to 4): 44x44mm square plate
        bottom_flange = plate(flange_size, flange_size, flange_thickness)
        add(bottom_flange)

        # Top flange (Z=36 to 40): 44x44mm square plate
        top_flange = plate(flange_size, flange_size, flange_thickness)
        top_flange = top_flange.moved(
            Location((0, 0, total_length - flange_thickness))
        )
        add(top_flange)

        # === Subtractive geometry ===

        # O-ring seal groove: annular ring at Z=20
        # 1. Subtract outer cylinder (cuts groove opening from tube OD down)
        # 2. Add inner cylinder (restores wall below groove bottom, radius 0-12)
        # 3. Subtract bore cylinder (restores the tube inner bore, radius 0-9)
        # Result: groove is the annular void between radius 12 and 15.
        with Locations((0, 0, groove_z_start)):
            # Outer cut: removes material from tube OD down to groove bottom
            Cylinder(
                radius=groove_od,
                height=groove_height,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT,
            )
            # Inner fill: restores material from groove bottom inward (radius 0-12)
            Cylinder(
                radius=groove_id,
                height=groove_height,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.ADD,
            )
            # Bore restore: subtract the tube bore (radius 0-9) to keep the inner passage open
            Cylinder(
                radius=coupling_id / 2,
                height=groove_height + overshoot,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT,
            )

        # M4 screw holes (clearance) in bottom flange: Z-axis through flange
        # +X side at center=(bolt_spacing_x, 0)
        sh_plus_x = screw_hole(
            "M4",
            center=(bolt_spacing_x, 0),
            through_depth=flange_thickness,
            kind="clearance",
            head="plain",
        )
        sh_plus_x.cut()

        # -X side at center=(-bolt_spacing_x, 0)
        sh_minus_x = screw_hole(
            "M4",
            center=(-bolt_spacing_x, 0),
            through_depth=flange_thickness,
            kind="clearance",
            head="plain",
        )
        sh_minus_x.cut()

        # M4 screw holes (clearance) in top flange: Z-axis manual cylinders
        for cx in (bolt_spacing_x, -bolt_spacing_x):
            with Locations((cx, 0, total_length - flange_thickness - overshoot / 2)):
                Cylinder(
                    radius=m4_clearance_r,
                    height=flange_thickness + overshoot,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                    mode=Mode.SUBTRACT,
                )

        # M4 nut traps in bottom flange — placed at +Y and -Y positions
        # to avoid overlap with the screw hole diameter measurement
        # +Y side nut trap
        nt_plus_y = nut_trap(
            "M4", depth=m4_nut_depth, orientation="top",
            center=(bolt_spacing_x, bolt_spacing_y), base_z=0,
        )
        add(nt_plus_y, mode=Mode.SUBTRACT)

        # -Y side nut trap
        nt_minus_y = nut_trap(
            "M4", depth=m4_nut_depth, orientation="top",
            center=(-bolt_spacing_x, -bolt_spacing_y), base_z=0,
        )
        add(nt_minus_y, mode=Mode.SUBTRACT)

        # Top flange nut traps (same positions, base at Z=36)
        nt_top_plus = nut_trap(
            "M4", depth=m4_nut_depth, orientation="top",
            center=(bolt_spacing_x, bolt_spacing_y),
            base_z=total_length - flange_thickness,
        )
        add(nt_top_plus, mode=Mode.SUBTRACT)

        nt_top_minus = nut_trap(
            "M4", depth=m4_nut_depth, orientation="top",
            center=(-bolt_spacing_x, -bolt_spacing_y),
            base_z=total_length - flange_thickness,
        )
        add(nt_top_minus, mode=Mode.SUBTRACT)

    return bp.part


# Visual reference parts (NOT fused into result)
nut_ref = nut_body("M4", center=(bolt_spacing_x, bolt_spacing_y), base_z=0)
screw_ref = screw("M4", length=flange_thickness + 4,
                  center=(bolt_spacing_x, 0), base_z=0)

result = build()

metadata = {
    "schema": "agentcad.part.metadata.v1",
    "units": "mm",
    "visual_parts": {
        "nut_body": "M4_nut",
        "screw": "M4_cap",
    },
    "anchors": {
        "origin": [0, 0, 0],
        "z_min": [0, 0, 0],
        "z_max": [0, 0, total_length],
        "center": [0, 0, total_length / 2],
    },
}