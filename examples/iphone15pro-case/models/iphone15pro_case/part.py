"""iPhone 15 Pro slim protective case — v2.

Sources:
  - Apple official body: 146.6 × 70.6 × 8.25 mm (apple.com/iphone-15-pro/specs)
  - MFi CAD leak (9to5Mac, 2023-04): camera array 38×37.5 mm, bump +3.78 mm,
    action button pill ends Ø2.42 mm / 3.51 mm span, volume Ø2.65 mm / 23.5 mm span.
  - Body corner radius ≈ 13 mm (superellipse fit from community 3D-print case data).

Coordinate frame (AgentCAD convention):
  +X  right   (short axis of phone as held in portrait)
  +Y  up toward phone top (long axis)
  +Z  from phone back toward display face

Layout along Z:
  Z = 0                          back face of case
  Z = wall_back                  inner cavity floor (= phone back + clearance)
  Z = wall_back + inner_d        phone display face level
  Z = outer_d (= wall_back + inner_d + lip_height)
                                 top opening — display fully exposed, small screen lip

Phone centred at (X=0, Y=0). Camera island in upper-left quadrant (–X, +Y) of back face.
"""
from __future__ import annotations

import json
from pathlib import Path

from build123d import *

PARAMS = json.loads((Path(__file__).with_name("params.json")).read_text(encoding="utf-8"))

# ── Phone body (Apple official) ──────────────────────────────────────────────
phone_h = float(PARAMS["phone_height"])          # 146.6 mm
phone_w = float(PARAMS["phone_width"])           # 70.6  mm
phone_d = float(PARAMS["phone_depth"])           # 8.25  mm
phone_r = float(PARAMS["phone_corner_radius"])   # 13.0  mm — corrected (prev. 22 mm)
cam_bump = float(PARAMS["camera_bump_height"])   # 3.78  mm above phone body

# ── Fit clearance ─────────────────────────────────────────────────────────────
fit_xy   = float(PARAMS["fit_xy"])               # 0.3 mm each side
fit_back = float(PARAMS["fit_back"])             # 0.3 mm at back

# ── Case wall geometry ────────────────────────────────────────────────────────
wall_side = float(PARAMS["wall_side"])           # 2.0 mm
wall_back = float(PARAMS["wall_back"])           # 1.5 mm
lip_h     = float(PARAMS["lip_height"])          # 1.2 mm

# ── Derived dimensions ────────────────────────────────────────────────────────
inner_w = phone_w + 2 * fit_xy    # 71.2 mm  inner cavity width
inner_h = phone_h + 2 * fit_xy    # 147.2 mm inner cavity height
inner_d = phone_d + fit_back      # 8.55  mm inner cavity depth

outer_w = inner_w + 2 * wall_side  # 75.2 mm
outer_h = inner_h + 2 * wall_side  # 151.2 mm
outer_d = wall_back + inner_d + lip_h  # 11.25 mm

# Corner radii — outer follows inner plus one wall thickness.
outer_r = phone_r + wall_side   # 15.0 mm
inner_r = phone_r               # 13.0 mm  (= phone body radius)

# ── Camera island cutout ──────────────────────────────────────────────────────
# MFi CAD: array 38 × 37.5 mm. Cutout sized 40 × 39.5 mm (+2 mm margin each side).
# Center: 20 mm from phone left edge → X_body_left = –phone_w/2 = –35.3 → cam_cx = –35.3+20 = –15.3
#         20 mm from phone top edge  → Y_body_top  = +phone_h/2 = +73.3 → cam_cy = +73.3–20 = +53.3
# In case coords (same origin): cam_cx = –15.3 + small nudge, cam_cy = +53.3.
# NOTE: The cutout is in the BACK PANEL (Z = 0 → wall_back). The bump (3.78 mm) sits
#       inside the inner cavity where there is no obstruction.
cam_cw  = float(PARAMS["cam_cutout_width"])    # 40.0 mm
cam_ch  = float(PARAMS["cam_cutout_height"])   # 39.5 mm
cam_cr  = float(PARAMS["cam_cutout_radius"])   # 10.0 mm corner radius
cam_cx  = float(PARAMS["cam_center_x"])        # –10.3 mm (left of case centre)
cam_cy  = float(PARAMS["cam_center_y"])        # +53.3 mm (near case top)

# ── Port cutouts ──────────────────────────────────────────────────────────────
usbc_w  = float(PARAMS["usbc_width"])       # 9.5 mm  USB-C port
usbc_h  = float(PARAMS["usbc_height"])      # 3.5 mm
spk_w   = float(PARAMS["speaker_width"])    # 14.0 mm speaker grill
spk_h   = float(PARAMS["speaker_height"])   # 3.0 mm
spk_ox  = float(PARAMS["speaker_offset_x"]) # –17.0 mm (left of centre, bottom edge)
mic_w   = float(PARAMS["mic_width"])        # 3.5 mm  microphone slot
mic_h   = float(PARAMS["mic_height"])       # 3.0 mm
mic_ox  = float(PARAMS["mic_offset_x"])     # +17.0 mm (right of centre, bottom edge)

# ── Button cutouts ─────────────────────────────────────────────────────────────
act_len = float(PARAMS["action_btn_len"])    # 8.5 mm  pill height
act_w   = float(PARAMS["action_btn_w"])      # 4.5 mm  pill width (through-wall depth)
act_y   = float(PARAMS["action_btn_y"])      # 55.5 mm above case centre (left rail)

vu_len  = float(PARAMS["vol_up_len"])        # 12.0 mm  Volume Up
vu_w    = float(PARAMS["vol_up_w"])          # 4.5 mm
vu_y    = float(PARAMS["vol_up_y"])          # 37.0 mm above centre (left rail)

vd_len  = float(PARAMS["vol_dn_len"])        # 12.0 mm  Volume Down
vd_w    = float(PARAMS["vol_dn_w"])          # 4.5 mm
vd_y    = float(PARAMS["vol_dn_y"])          # 20.0 mm above centre (left rail)

pw_len  = float(PARAMS["power_btn_len"])     # 22.0 mm  Power/Side
pw_w    = float(PARAMS["power_btn_w"])       # 4.5 mm
pw_y    = float(PARAMS["power_btn_y"])       # 13.0 mm above centre (right rail)

# Z-span for button slots: cover full inner depth plus small overcut.
btn_z_ctr  = wall_back + inner_d / 2   # midpoint of phone thickness in case Z
btn_z_span = inner_d + 0.4             # slot height in Z (through full side wall)


def _left_slot(
    part_ctx: BuildPart,
    y_center: float,
    btn_length: float,
    btn_depth: float,
) -> None:
    """Subtract a rounded pill slot through the left side wall."""
    # The left outer wall face is at X = –outer_w/2.
    # Align.MIN means the box minimum-X face sits at the Location X.
    slot_r = min(btn_depth, btn_length) / 2 - 0.05
    with Locations((-(outer_w / 2) - 0.1, y_center, btn_z_ctr)):
        Box(
            wall_side + 0.2,
            btn_length,
            btn_z_span,
            align=(Align.MIN, Align.CENTER, Align.CENTER),
            mode=Mode.SUBTRACT,
        )


def _right_slot(
    part_ctx: BuildPart,
    y_center: float,
    btn_length: float,
    btn_depth: float,
) -> None:
    """Subtract a slot through the right side wall."""
    with Locations(((outer_w / 2) + 0.1, y_center, btn_z_ctr)):
        Box(
            wall_side + 0.2,
            btn_length,
            btn_z_span,
            align=(Align.MAX, Align.CENTER, Align.CENTER),
            mode=Mode.SUBTRACT,
        )


def _bottom_slot(y_outer: float, x_center: float, slot_w: float, slot_h: float) -> None:
    """Subtract a horizontal slot through the bottom wall (Y direction)."""
    # Location is just outside the outer bottom wall. Align.MIN places the
    # MIN-Y face of the box there, so the box extends inward (+Y) through
    # the wall_side-thick bottom wall and slightly into the inner cavity.
    with Locations((x_center, y_outer - 0.1, btn_z_ctr)):
        Box(
            slot_w,
            wall_side + 0.2,
            slot_h,
            align=(Align.CENTER, Align.MIN, Align.CENTER),
            mode=Mode.SUBTRACT,
        )


def build() -> object:
    with BuildPart() as case:

        # ── 1. Outer shell ──────────────────────────────────────────────────
        with BuildSketch(Plane.XY):
            RectangleRounded(outer_w, outer_h, outer_r)
        extrude(amount=outer_d)

        # ── 2. Inner cavity (open at display face, Z = outer_d) ─────────────
        # NOTE: Locations + BuildSketch + extrude does NOT apply the Z offset
        # to the sketch plane. Must use an explicit Plane to position correctly.
        with BuildSketch(Plane(origin=(0, 0, wall_back))):
            RectangleRounded(inner_w, inner_h, inner_r)
        extrude(amount=inner_d + lip_h + 0.1, mode=Mode.SUBTRACT)

        # ── 3. Camera island cutout through back panel ───────────────────────
        # Back panel: Z = 0 to wall_back (1.5 mm).
        # Sketch plane is placed 0.1 mm below the outer back face; extrude
        # extends 0.2 mm past wall_back for a clean through-cut.
        with BuildSketch(Plane(origin=(cam_cx, cam_cy, -0.1))):
            RectangleRounded(cam_cw, cam_ch, cam_cr)
        extrude(amount=wall_back + 0.2, mode=Mode.SUBTRACT)

        # ── 4. USB-C port — bottom edge, centred ────────────────────────────
        _bottom_slot(-(outer_h / 2), 0.0, usbc_w, usbc_h)

        # ── 5. Speaker grill — bottom edge, left of centre ──────────────────
        _bottom_slot(-(outer_h / 2), spk_ox, spk_w, spk_h)

        # ── 6. Microphone slot — bottom edge, right of centre ───────────────
        _bottom_slot(-(outer_h / 2), mic_ox, mic_w, mic_h)

        # ── 7. Action button — left rail, near top ───────────────────────────
        _left_slot(case, act_y, act_len, act_w)

        # ── 8. Volume Up — left rail ─────────────────────────────────────────
        _left_slot(case, vu_y, vu_len, vu_w)

        # ── 9. Volume Down — left rail ───────────────────────────────────────
        _left_slot(case, vd_y, vd_len, vd_w)

        # ── 10. Power / Side button — right rail ─────────────────────────────
        _right_slot(case, pw_y, pw_len, pw_w)

    return case.part


result = build()

metadata = {
    "schema": "agentcad.part.metadata.v1",
    "model": "iphone15pro_case",
    "compatible_with": "iPhone 15 Pro (A17 Pro, 2023)",
    "sources": [
        "Apple official dimensions: 146.6 x 70.6 x 8.25 mm",
        "MFi CAD leak (9to5Mac 2023-04): camera 38x37.5mm, bump +3.78mm",
        "Body corner radius ~13mm from community 3D-case data",
    ],
    "phone_body_mm": {"w": phone_w, "h": phone_h, "d": phone_d},
    "phone_corner_radius_mm": phone_r,
    "fit_clearance_mm": fit_xy,
    "case_outer_mm": {"w": outer_w, "h": outer_h, "d": outer_d},
    "case_wall_mm": {"side": wall_side, "back": wall_back, "lip": lip_h},
    "camera_cutout_mm": {"w": cam_cw, "h": cam_ch, "cx": cam_cx, "cy": cam_cy},
}
