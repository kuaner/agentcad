import json
from pathlib import Path

from build123d import *

PARAMS = json.loads(
    Path(__file__).with_name("params.json").read_text(encoding="utf-8")
)

base_width = float(PARAMS["base_width"])         # 50mm, X direction
base_depth = float(PARAMS["base_depth"])         # 40mm, Y direction
base_thickness = float(PARAMS["base_thickness"]) # 4mm, Z direction
wall_height = float(PARAMS["wall_height"])       # 30mm, Z direction
wall_thickness = float(PARAMS["wall_thickness"]) # 4mm, Y direction
hole_diameter = float(PARAMS["hole_diameter"])   # 4.5mm
hole_r = hole_diameter / 2                       # 2.25mm
base_hole_x = float(PARAMS["base_hole_x_offset"]) # 15mm
base_hole_y = float(PARAMS["base_hole_y_offset"]) # 15mm
upright_hole_z = float(PARAMS["upright_hole_z"])   # 20mm

# Layout:
#   Base plate:    X[-25, +25], Y[-20, +20], Z[0, 4]
#   Upright wall:  X[-25, +25], Y[16, +20],  Z[0, 30]
#   Total bbox:    50 x 40 x 30

wall_y_center = base_depth / 2 - wall_thickness / 2  # Y=18 (center of wall)
wall_z_center = wall_height / 2                       # Z=15 (center of wall)

with BuildPart() as bp:
    # Base plate: sits on Z=0, centered in X and Y
    Box(base_width, base_depth, base_thickness,
        align=(Align.CENTER, Align.CENTER, Align.MIN))

    # Upright wall at back edge: placed via Locations to avoid double-add.
    # Using Locations + Box (center-aligned) positions wall cleanly.
    with Locations((0, wall_y_center, wall_z_center)):
        Box(base_width, wall_thickness, wall_height)

    # Base plate holes: two M4 clearance holes (⌀4.5mm), through full 4mm thickness
    # Placed from Z=0 upward with Align.MIN so they cut through Z[0, base_thickness]
    with Locations((-base_hole_x, base_hole_y, 0), (base_hole_x, base_hole_y, 0)):
        Cylinder(radius=hole_r, height=base_thickness + 0.1,
                 align=(Align.CENTER, Align.CENTER, Align.MIN),
                 mode=Mode.SUBTRACT)

    # Upright wall hole: one M4 clearance hole (⌀4.5mm) through 4mm wall in Y direction
    # rotation=(90,0,0) aligns cylinder axis with Y; centered at wall Y and upright_hole_z
    with Locations((0, wall_y_center, upright_hole_z)):
        Cylinder(radius=hole_r, height=wall_thickness + 0.1,
                 rotation=(90, 0, 0),
                 align=(Align.CENTER, Align.CENTER, Align.CENTER),
                 mode=Mode.SUBTRACT)

result = bp.part
