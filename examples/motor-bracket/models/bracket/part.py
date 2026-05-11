"""NEMA17 L-bracket: base plate with panel mount, vertical web with motor mount,
nut trap, cable slot, rounded base edges, and triangular gussets.

Tunable values live in params.json. The final geometry must be assigned to
global variable `result`.
"""
import json
import math
from pathlib import Path

from build123d import *

PARAMS = json.loads(
    Path(__file__).with_name("params.json").read_text(encoding="utf-8")
)

base_width = float(PARAMS["base_width"])       # 50
base_depth = float(PARAMS["base_depth"])        # 55
base_thickness = float(PARAMS["base_thickness"]) # 5
web_thickness = float(PARAMS["web_thickness"])  # 5
web_height = float(PARAMS["web_height"])        # 42
rounding_size = float(PARAMS["rounding_size"])  # 3
gusset_depth = float(PARAMS["gusset_depth"])    # 12
gusset_height = float(PARAMS["gusset_height"])  # 12
nema_center_z = float(PARAMS["nema_center_z"])  # 26
nut_trap_depth = float(PARAMS["nut_trap_depth"]) # 4
slot_width = float(PARAMS["slot_width"])         # 5
slot_depth = float(PARAMS["slot_depth"])          # 3
slot_height = float(PARAMS["slot_height"])        # 30

# Derived constants
half_bw = base_width / 2    # 25
half_bd = base_depth / 2    # 27.5
overshoot = 1.0

# NEMA17 standard dimensions
nema_bore_r = 11.0          # 22mm center bore radius
nema_spacing = 31.0         # screw hole spacing
nema_screw_r = 1.6          # M3 clearance radius (3.2mm diameter)
half_nema = nema_spacing / 2  # 15.5

# M3 clearance hole radius for panel mount
m3_clearance_r = 1.6        # 3.2mm diameter

# M3 nut across-flats and circumradius
m3_nut_af = 5.5
m3_nut_circum_r = m3_nut_af / 2 / math.cos(math.radians(30))  # ~3.175mm

# Panel mount hole positions (rectangular, centered toward front of base)
panel_positions = [
    (-18, -20),   # front-left
    (18, -20),    # front-right
    (-18, 4),     # back-left
    (18, 4),      # back-right
]

# NEMA17 screw hole positions (X, Z) relative to bracket origin
nema_screw_positions = [
    (-half_nema, nema_center_z - half_nema),   # lower-left
    (half_nema, nema_center_z - half_nema),     # lower-right
    (-half_nema, nema_center_z + half_nema),    # upper-left
    (half_nema, nema_center_z + half_nema),     # upper-right
]

# Nut trap position (on web outer face, Y-axis approach)
nut_x = 20.0
nut_z = 35.0

# Cable slot position (on web outer face, Y-axis approach)
slot_x = -21.0
slot_z_start = 10.0

# Gusset width along X
gusset_w = 8.0


def build():
    with BuildPart() as bp:
        # ===== 1. BASE PLATE (horizontal) =====
        add(Box(base_width, base_depth, base_thickness,
                align=(Align.CENTER, Align.CENTER, Align.MIN)))

        # ===== 2. ROUND BASE PLATE BOTTOM EDGES =====
        # Select edges at Z≈0 (bottom of base plate), exclude the back edge
        # near the web junction (Y near half_bd)
        all_bottom = [e for e in bp.edges()
                      if abs(e.center().Z) < 0.1
                      and e.geom_type == GeomType.LINE]
        # Keep front and side bottom edges; drop back edge at Y≈half_bd
        roundable = [e for e in all_bottom
                     if e.center().Y < half_bd - 1.0]
        if roundable:
            fillet(roundable, radius=rounding_size)

        # ===== 3. VERTICAL WEB (at back edge, rising from base top) =====
        with Locations((0, half_bd, base_thickness)):
            Box(base_width, web_thickness, web_height,
                align=(Align.CENTER, Align.MIN, Align.MIN))

        # ===== 4. GUSSETS (triangular reinforcement at base-web junction) =====
        # Left gusset: sketch on YZ plane at X = -half_bw + gusset_w
        with BuildSketch(Plane.YZ.offset(-half_bw + gusset_w)):
            Polygon([
                (half_bd, base_thickness),
                (half_bd - gusset_depth, base_thickness),
                (half_bd, base_thickness + gusset_height),
            ])
        extrude(amount=gusset_w)

        # Right gusset: sketch on YZ plane at X = half_bw - gusset_w
        with BuildSketch(Plane.YZ.offset(half_bw - gusset_w)):
            Polygon([
                (half_bd, base_thickness),
                (half_bd - gusset_depth, base_thickness),
                (half_bd, base_thickness + gusset_height),
            ])
        extrude(amount=gusset_w)

        # ===== 5. NEMA17 MOUNT HOLES (Y-axis through web) =====
        # Center bore: 22mm diameter
        with Locations((0, half_bd - overshoot / 2, nema_center_z)):
            Cylinder(radius=nema_bore_r,
                     height=web_thickness + overshoot,
                     rotation=(90, 0, 0),
                     align=(Align.CENTER, Align.CENTER, Align.MIN),
                     mode=Mode.SUBTRACT)

        # 4 M3 clearance screw holes on 31mm square pattern
        for sx, sz in nema_screw_positions:
            with Locations((sx, half_bd - overshoot / 2, sz)):
                Cylinder(radius=nema_screw_r,
                         height=web_thickness + overshoot,
                         rotation=(90, 0, 0),
                         align=(Align.CENTER, Align.CENTER, Align.MIN),
                         mode=Mode.SUBTRACT)

        # ===== 6. PANEL MOUNT HOLES (Z-axis through base plate) =====
        for px, py in panel_positions:
            with Locations((px, py, -overshoot / 2)):
                Cylinder(radius=m3_clearance_r,
                         height=base_thickness + overshoot,
                         align=(Align.CENTER, Align.CENTER, Align.MIN),
                         mode=Mode.SUBTRACT)

        # ===== 7. M3 NUT TRAP (Y-axis hex pocket on web outer face) =====
        hex_pts = [(m3_nut_circum_r * math.cos(math.radians(60 * i)),
                     m3_nut_circum_r * math.sin(math.radians(60 * i)))
                    for i in range(6)]

        # Sketch on XZ plane at Y = outer face + overshoot/2
        # Plane: origin at nut position, normal along -Y (extrude into web)
        with BuildSketch(Plane(
            origin=(nut_x, half_bd + web_thickness + overshoot / 2, nut_z),
            x_dir=(1, 0, 0),
            z_dir=(0, -1, 0),
        )):
            Polygon(hex_pts)
        extrude(amount=nut_trap_depth + overshoot, mode=Mode.SUBTRACT)

        # ===== 8. CABLE SLOT (rectangular, Y-axis into web from outer face) =====
        with Locations((slot_x, half_bd + web_thickness, slot_z_start)):
            Box(slot_width, slot_depth, slot_height,
                align=(Align.CENTER, Align.MAX, Align.MIN),
                mode=Mode.SUBTRACT)

    return bp.part


result = build()
metadata = {
    "schema": "agentcad.part.metadata.v1",
    "units": "mm",
    "anchors": {
        "origin": [0, 0, 0],
        "base_center": [0, 0, 2.5],
        "motor_center": [0, half_bd + web_thickness / 2, nema_center_z],
    },
}