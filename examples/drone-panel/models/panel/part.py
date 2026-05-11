"""Drone frame lightweight panel.

Features:
- Solid base plate with filleted corners (pie_slice equivalent)
- rect_tube border (outer wall minus inner cavity)
- sparse_wall: grid infill core for weight reduction
- hex_panel: honeycomb heat dissipation zone in center
- torus: seal ring groove at edge (subtractive)

Tunable values live in params.json. The final geometry must be assigned to
global variable `result`.
"""
import json
import math
from pathlib import Path

from build123d import *

from agentcad.features import sparse_wall, hex_panel, torus

PARAMS = json.loads((Path(__file__).with_name("params.json")).read_text(encoding="utf-8"))

panel_width = float(PARAMS["panel_width"])
panel_depth = float(PARAMS["panel_depth"])
panel_height = float(PARAMS["panel_height"])
infill_height = float(PARAMS["infill_height"])
sparse_strut = float(PARAMS["sparse_strut"])
sparse_spacing = float(PARAMS["sparse_spacing"])
corner_radius = float(PARAMS["corner_radius"])
border_wall = float(PARAMS["border_wall"])
border_height = float(PARAMS["border_height"])
hex_strut = float(PARAMS["hex_strut"])
hex_spacing = float(PARAMS["hex_spacing"])
hex_size_x = float(PARAMS["hex_size_x"])
hex_size_y = float(PARAMS["hex_size_y"])
hex_height = float(PARAMS["hex_height"])
seal_major_radius = float(PARAMS["seal_major_radius"])
seal_minor_radius = float(PARAMS["seal_minor_radius"])
seal_offset_y = float(PARAMS["seal_offset_y"])

half_w = panel_width / 2
half_d = panel_depth / 2
total_height = panel_height + border_height

# Inner dimensions of the border (where the infill lives)
inner_w = panel_width - 2 * border_wall
inner_d = panel_depth - 2 * border_wall


def build():
    # Step 1: Build a solid rectangular plate with rounded corners
    with BuildPart() as bp:
        # Solid base plate
        Box(panel_width, panel_depth, total_height,
            align=(Align.CENTER, Align.CENTER, Align.MIN))

        # Fillet the four vertical corner edges for rounded corners
        all_edges = bp.edges()
        z_edges = all_edges.filter_by(GeomType.LINE).filter_by(Axis.Z)

        corner_edges = []
        for e in z_edges:
            c = e.center()
            cx, cy = c.X, c.Y
            for corner_x, corner_y in [
                (-half_w, -half_d),
                (half_w, -half_d),
                (-half_w, half_d),
                (half_w, half_d),
            ]:
                if abs(cx - corner_x) < 0.5 and abs(cy - corner_y) < 0.5:
                    corner_edges.append(e)
                    break

        if corner_edges:
            fillet(corner_edges, radius=corner_radius)

        # Step 2: Subtract the inner cavity to create the rect_tube border
        # Only carve to infill_height so border walls have a lip above for cover seating
        overshoot = 1.0
        Box(inner_w, inner_d, infill_height + overshoot,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
            mode=Mode.SUBTRACT).moved(Location((0, 0, -overshoot / 2)))

        # Step 3: Add sparse_wall grid infill core inside the cavity (lower than border)
        core = sparse_wall(
            (inner_w, inner_d, infill_height),
            strut=sparse_strut,
            spacing=sparse_spacing,
            center=(0, 0),
            base_z=0,
        )
        add(core)

        # Step 4: Add hex_panel honeycomb zone in center (lower than border)
        hex_zone = hex_panel(
            (hex_size_x, hex_size_y, infill_height),
            strut=hex_strut,
            spacing=hex_spacing,
            center=(0, 0),
            base_z=0,
        )
        add(hex_zone)

        # Step 5: Subtract the torus seal ring groove
        seal_ring = torus(
            major_radius=seal_major_radius,
            minor_radius=seal_minor_radius,
            center=(0, seal_offset_y),
            base_z=panel_height / 2,
        )
        add(seal_ring, mode=Mode.SUBTRACT)

    return bp.part


result = build()
metadata = {
    "schema": "agentcad.part.metadata.v1",
    "units": "mm",
    "anchors": {
        "origin": [0, 0, 0],
        "center": [0, 0, total_height / 2],
        "x_min": [-half_w, 0, 0],
        "x_max": [half_w, 0, 0],
    },
}