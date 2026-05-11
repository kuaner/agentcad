"""Planetary gear reducer housing.

Features: ring_gear (24 teeth, module=2), spur_gear (sun, 12 teeth, module=2),
tube (bearing seat), rect_tube (outer wall), threaded_nut (M8 shaft fix).

Uses sequential .fuse() and .cut() to ensure all parts merge into one Solid,
avoiding boundary edges that occur when BuildPart add() leaves touching but
non-overlapping parts as separate bodies.

The final geometry must be assigned to global variable `result`.
"""
import json
import math
from pathlib import Path

from build123d import *

from agentcad.features import ring_gear, spur_gear, tube, rect_tube, nut_body

PARAMS = json.loads(
    (Path(__file__).with_name("params.json")).read_text(encoding="utf-8")
)

# --- Read params ---
ring_teeth = int(PARAMS["ring_teeth"])
ring_module = float(PARAMS["ring_module"])
ring_thickness = float(PARAMS["ring_thickness"])
ring_rim_width = float(PARAMS["ring_rim_width"])
sun_teeth = int(PARAMS["sun_teeth"])
sun_module = float(PARAMS["sun_module"])
sun_thickness = float(PARAMS["sun_thickness"])
sun_shaft_d = float(PARAMS["sun_shaft_diameter"])
tube_od = float(PARAMS["tube_od"])
tube_id = float(PARAMS["tube_id"])
tube_height = float(PARAMS["tube_height"])
rect_w = float(PARAMS["rect_width"])
rect_d = float(PARAMS["rect_depth"])
rect_h = float(PARAMS["rect_height"])
rect_wall = float(PARAMS["rect_wall"])
nut_spec = PARAMS["nut_spec"]

# --- Compute key radii ---
ring_r_p = ring_module * ring_teeth / 2          # 24.0 mm
ring_r_root = ring_r_p + 1.25 * ring_module      # 26.5 mm
ring_r_tip = ring_r_p - ring_module               # 22.0 mm
ring_r_outer = ring_r_root + ring_rim_width       # 34.5 mm

sun_r_p = sun_module * sun_teeth / 2              # 12.0 mm
sun_r_tip = sun_r_p + sun_module                  # 14.0 mm

rect_inner_w = rect_w - 2 * rect_wall             # 70.0 mm
rect_inner_d = rect_d - 2 * rect_wall             # 70.0 mm

# Small overlap margin to ensure boolean fuse merges touching faces
OVERLAP = 0.1  # mm


def build():
    # Create individual feature helpers (without builder=b for composite part)
    rg = ring_gear(
        ring_teeth, ring_module, ring_thickness,
        rim_width=ring_rim_width,
    )
    sg = spur_gear(
        sun_teeth, sun_module, sun_thickness,
        shaft_diameter=sun_shaft_d,
    )
    bt = tube(tube_od, tube_id, tube_height)
    rt = rect_tube((rect_w, rect_d, rect_h), wall=rect_wall)
    tn = nut_body(nut_spec, base_z=rect_h)

    # Fill piece: bridges the gap between ring_gear outer rim (34.5mm radius)
    # and rect_tube inner wall (35mm from center on flat sides).
    # Slightly oversized (71x71 instead of 70x70) to overlap into the
    # rect_tube wall. Inner bore slightly undersized (34.4 instead of 34.5)
    # so the ring_gear rim overlaps into the fill.
    with BuildPart(mode=Mode.PRIVATE) as fill_bp:
        Box(
            rect_inner_w + 1, rect_inner_d + 1, rect_h,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )
        Cylinder(
            radius=ring_r_outer - OVERLAP,
            height=rect_h + 1,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
            mode=Mode.SUBTRACT,
        ).moved(Location((0, 0, -0.5)))
    fill = fill_bp.part

    # Bottom closing plate: annular ring from sun_gear tip to ring_gear tip.
    # Seals the gear chamber at Z=0, connecting sun gear outer surface to
    # ring gear inner surface. Oversized by OVERLAP on both edges to ensure
    # the plate fuses with adjacent gear bodies.
    plate_thick = 1.0

    with BuildPart(mode=Mode.PRIVATE) as bottom_close_bp:
        Cylinder(
            radius=ring_r_tip + OVERLAP,
            height=plate_thick,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )
        Cylinder(
            radius=sun_r_tip - OVERLAP,
            height=plate_thick + 1,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
            mode=Mode.SUBTRACT,
        ).moved(Location((0, 0, -0.5)))
    bottom_close = bottom_close_bp.part

    # Top closing plate: same annular ring at Z = rect_h - plate_thick
    with BuildPart(mode=Mode.PRIVATE) as top_close_bp:
        Cylinder(
            radius=ring_r_tip + OVERLAP,
            height=plate_thick,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        ).moved(Location((0, 0, rect_h - plate_thick)))
        Cylinder(
            radius=sun_r_tip - OVERLAP,
            height=plate_thick + 1,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
            mode=Mode.SUBTRACT,
        ).moved(Location((0, 0, rect_h - plate_thick - 0.5)))
    top_close = top_close_bp.part

    # Sequential fuse: start with rect_tube, add each feature with overlap
    housing = rt
    housing = housing.fuse(fill)
    housing = housing.fuse(rg)
    housing = housing.fuse(sg)
    housing = housing.fuse(bt)
    housing = housing.fuse(bottom_close)
    housing = housing.fuse(top_close)
    housing = housing.fuse(tn)

    # Subtract shaft bore through entire height (Z=0 to Z=11.5+)
    # with 1mm overshoot at both ends for clean subtraction.
    bore_r = tube_id / 2
    bore_height = rect_h + 6.5 + 1  # housing height + nut height + overshoot
    with BuildPart(mode=Mode.PRIVATE) as bore_bp:
        Cylinder(
            radius=bore_r,
            height=bore_height,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        ).moved(Location((0, 0, -0.5)))
    bore = bore_bp.part

    housing = housing.cut(bore)

    return housing


result = build()
metadata = {
    "schema": "agentcad.part.metadata.v1",
    "units": "mm",
    "anchors": {
        "origin": [0, 0, 0],
        "ring_pitch_radius": [ring_r_p, 0, 0],
        "sun_pitch_radius": [sun_r_p, 0, 0],
    },
}