"""Cross-section extraction and 2D SVG rendering from STL meshes.

Slices a 3D mesh with an axis-aligned plane and returns either raw line
segments (for numerical analysis) or an SVG string (for visual inspection
with LLM vision tools).  Supports X, Y, and Z cutting planes.
"""
from __future__ import annotations

from pathlib import Path

from .stl import Triangle

# Axis constants — match array index in 3D vertex tuples.
AXIS_X = 0
AXIS_Y = 1
AXIS_Z = 2

# 2D plane labels: (horizontal_axis_label, vertical_axis_label, plane_name)
_PLANE_LABELS: dict[int, tuple[str, str, str]] = {
    AXIS_X: ("Y (mm)", "Z (mm)", "YZ plane"),
    AXIS_Y: ("X (mm)", "Z (mm)", "XZ plane"),
    AXIS_Z: ("X (mm)", "Y (mm)", "XY plane"),
}
_AXIS_NAME = {AXIS_X: "X", AXIS_Y: "Y", AXIS_Z: "Z"}

Segment2D = tuple[tuple[float, float], tuple[float, float]]


# ── Segment extraction ────────────────────────────────────────────────────────

def section_segments(
    triangles: list[Triangle],
    axis: int,
    value: float,
) -> list[Segment2D]:
    """Extract 2D line segments where the mesh intersects an axis-aligned plane.

    ``axis``: 0=X (YZ plane), 1=Y (XZ plane), 2=Z (XY plane).

    Each triangle that straddles the plane contributes one line segment.
    Returns segments in the 2D coordinate system of the cut plane:
      - Z cut  → (X, Y)
      - X cut  → (Y, Z)
      - Y cut  → (X, Z)
    """
    segs: list[Segment2D] = []
    for tri in triangles:
        seg = _tri_seg(tri, axis, value)
        if seg is not None:
            segs.append(seg)
    return segs


def _tri_seg(tri: Triangle, axis: int, value: float) -> Segment2D | None:
    """Intersect one triangle with an axis-aligned plane."""
    verts = list(tri)
    pts: list[tuple[float, float]] = []

    for i in range(3):
        p = verts[i]
        q = verts[(i + 1) % 3]
        dp = p[axis] - value
        dq = q[axis] - value

        if abs(dp) < 1e-8 and abs(dq) < 1e-8:
            # Both vertices on the plane: add both (edge lies on section).
            _add_unique(pts, _proj(p, axis))
            _add_unique(pts, _proj(q, axis))
        elif abs(dp) < 1e-8:
            _add_unique(pts, _proj(p, axis))
        elif abs(dq) < 1e-8:
            pass  # q will be handled as p in the next iteration
        elif (dp < 0) != (dq < 0):
            t = dp / (dp - dq)
            ix = p[0] + t * (q[0] - p[0])
            iy = p[1] + t * (q[1] - p[1])
            iz = p[2] + t * (q[2] - p[2])
            _add_unique(pts, _proj((ix, iy, iz), axis))

        if len(pts) == 2:
            return (pts[0], pts[1])

    return None


def _proj(pt: tuple, axis: int) -> tuple[float, float]:
    """Drop the section axis to get a 2D point in the cut plane."""
    if axis == AXIS_X:
        return (pt[1], pt[2])   # (Y, Z)
    if axis == AXIS_Y:
        return (pt[0], pt[2])   # (X, Z)
    return (pt[0], pt[1])       # (X, Y)


def _add_unique(pts: list[tuple[float, float]], p: tuple[float, float]) -> None:
    if not any(abs(p[0] - q[0]) < 1e-6 and abs(p[1] - q[1]) < 1e-6 for q in pts):
        pts.append(p)


# ── Profile scan ─────────────────────────────────────────────────────────────

def scan_profile(
    triangles: list[Triangle],
    axis: int = AXIS_Z,
    samples: int = 20,
    step_threshold: float = 2.0,
) -> dict:
    """Scan the mesh along an axis, measuring cross-section size at each position.

    At each sampled position, slices the mesh and reports the 2D bounding box
    of the intersection.  Detects *step changes* — positions where the section
    size changes abruptly — which mark feature boundaries (cavity starts, port
    openings, wall ends, etc.).

    Args:
        triangles: STL triangle list.
        axis: 0=X, 1=Y, 2=Z (scanning direction).
        samples: Number of evenly-spaced cross-sections to take.
        step_threshold: Minimum size change (mm) to count as a step change.

    Returns a dict with ``profile`` (list of per-position measurements) and
    ``step_changes`` (list of detected boundary positions).
    """
    if not triangles:
        return {"ok": False, "error": "no triangles"}

    all_vals = [v[axis] for tri in triangles for v in tri]
    pos_min = min(all_vals)
    pos_max = max(all_vals)

    if pos_max - pos_min < 1e-6:
        return {"ok": False, "error": f"zero extent along {_AXIS_NAME[axis]} axis"}

    margin = (pos_max - pos_min) * 0.02
    span = pos_max - pos_min - 2 * margin
    positions = [pos_min + margin + span * i / max(samples - 1, 1) for i in range(samples)]

    profile = []
    for pos in positions:
        segs = section_segments(triangles, axis, pos)
        if not segs:
            profile.append({
                "pos": round(pos, 3),
                "point_count": 0,
                "u_size": 0.0,
                "v_size": 0.0,
            })
            continue

        us = [p[0] for seg in segs for p in seg]
        vs = [p[1] for seg in segs for p in seg]
        u_size = max(us) - min(us)
        v_size = max(vs) - min(vs)
        profile.append({
            "pos": round(pos, 3),
            "point_count": len(segs) * 2,
            "u_size": round(u_size, 3),
            "v_size": round(v_size, 3),
            "u_min": round(min(us), 3),
            "u_max": round(max(us), 3),
            "v_min": round(min(vs), 3),
            "v_max": round(max(vs), 3),
        })

    # Point count threshold: catches hollow shells where outer bbox is constant
    # but interior surfaces appear (e.g. phone case cavity starting).
    max_pts = max((p["point_count"] for p in profile), default=1) or 1
    count_threshold = max(30, max_pts * 0.04)

    step_changes = []
    for i in range(1, len(profile)):
        prev = profile[i - 1]
        curr = profile[i]
        du = curr["u_size"] - prev["u_size"]
        dv = curr["v_size"] - prev["v_size"]
        dpts = curr["point_count"] - prev["point_count"]
        size_step = abs(du) > step_threshold or abs(dv) > step_threshold
        count_step = abs(dpts) >= count_threshold
        if size_step or count_step:
            pos_mid = round((prev["pos"] + curr["pos"]) / 2, 3)
            step_changes.append({
                "pos": pos_mid,
                "delta_u": round(du, 3),
                "delta_v": round(dv, 3),
                "delta_point_count": dpts,
                "hint": _step_hint(du, dv, dpts),
            })

    u_lbl, v_lbl, plane_lbl = _PLANE_LABELS[axis]
    return {
        "ok": True,
        "axis": _AXIS_NAME[axis],
        "plane_label": plane_lbl,
        "u_label": u_lbl,
        "v_label": v_lbl,
        "pos_range": [round(pos_min, 3), round(pos_max, 3)],
        "profile": profile,
        "step_changes": step_changes,
    }


def _step_hint(du: float, dv: float, dpts: int = 0) -> str:
    if du < -2 or dv < -2:
        return "section shrinks — possible cavity start or wall end"
    if du > 2 or dv > 2:
        return "section grows — possible feature addition or flange"
    if dpts > 0:
        return "more interior surfaces — inner cavity or new features begin here"
    if dpts < 0:
        return "fewer interior surfaces — inner cavity or features end here"
    return "geometry transition"


# ── SVG rendering ─────────────────────────────────────────────────────────────

def render_section_svg(
    segments: list[Segment2D],
    axis: int,
    value: float,
    canvas: int = 500,
    padding: int = 48,
) -> str:
    """Render cross-section line segments as an SVG string.

    The SVG is suitable for LLM vision inspection: dark lines on white
    background, annotated with axis labels, corner coordinates, and a scale bar.
    """
    u_lbl, v_lbl, plane_lbl = _PLANE_LABELS[axis]
    axis_name = _AXIS_NAME[axis]
    title = f"{axis_name} = {value:.2f} mm  ·  {plane_lbl}"

    if not segments:
        return _empty_svg(canvas, title)

    all_u = [p[0] for seg in segments for p in seg]
    all_v = [p[1] for seg in segments for p in seg]
    u_min, u_max = min(all_u), max(all_u)
    v_min, v_max = min(all_v), max(all_v)
    u_range = max(u_max - u_min, 1.0)
    v_range = max(v_max - v_min, 1.0)

    draw = canvas - 2 * padding
    scale = min(draw / u_range, draw / v_range)
    aw = u_range * scale
    ah = v_range * scale
    ox = padding + (draw - aw) / 2
    oy = padding + (draw - ah) / 2

    def to_svg(u: float, v: float) -> tuple[float, float]:
        return ox + (u - u_min) * scale, oy + ah - (v - v_min) * scale

    lines = []
    for (u1, v1), (u2, v2) in segments:
        x1, y1 = to_svg(u1, v1)
        x2, y2 = to_svg(u2, v2)
        lines.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="#1a1a2e" stroke-width="1.2" stroke-linecap="round"/>'
        )

    # Corner coordinate labels
    def txt(x: float, y: float, s: str, anchor: str = "middle") -> str:
        return (
            f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
            f'font-size="9" fill="#777" font-family="monospace">{s}</text>'
        )

    cw = canvas
    labels = [
        txt(ox,          oy + ah + 14, f"{u_min:.1f}", "start"),
        txt(ox + aw,     oy + ah + 14, f"{u_max:.1f}", "end"),
        txt(ox - 4,      oy + ah,      f"{v_min:.1f}", "end"),
        txt(ox - 4,      oy,           f"{v_max:.1f}", "end"),
        txt(ox + aw / 2, cw - 6,       u_lbl),
        (f'<text x="12" y="{oy + ah / 2:.1f}" text-anchor="middle" font-size="9" '
         f'fill="#777" font-family="sans-serif" '
         f'transform="rotate(-90 12 {oy + ah / 2:.1f})">{v_lbl}</text>'),
    ]

    # Scale bar
    bar_mm = _nice_bar(u_range)
    bar_px = bar_mm * scale
    bx = ox + aw - bar_px
    by = oy + ah + 26
    scale_bar = (
        f'<line x1="{bx:.1f}" y1="{by}" x2="{bx + bar_px:.1f}" y2="{by}" '
        f'stroke="#999" stroke-width="1.5"/>'
        f'<text x="{bx + bar_px / 2:.1f}" y="{by + 11}" text-anchor="middle" '
        f'font-size="9" fill="#999" font-family="sans-serif">{bar_mm:.0f} mm</text>'
    )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{cw}" height="{cw}">'
        f'<rect width="{cw}" height="{cw}" fill="white" rx="3"/>'
        f'<rect x="{ox:.1f}" y="{oy:.1f}" width="{aw:.1f}" height="{ah:.1f}" '
        f'fill="#f5f5f7" stroke="#e0e0e0" stroke-width="0.5"/>'
        f'<text x="{cw // 2}" y="18" text-anchor="middle" font-size="11" '
        f'font-weight="600" fill="#333" font-family="sans-serif">{title}</text>'
        f'<g>{"".join(lines)}</g>'
        f'{"".join(labels)}'
        f'{scale_bar}'
        f'</svg>'
    )


def write_section_svg(
    triangles: list[Triangle],
    axis: int,
    value: float,
    out_path: Path,
    canvas: int = 500,
) -> dict:
    """Extract section, render SVG, and write to disk.  Returns a result dict."""
    segs = section_segments(triangles, axis, value)
    svg = render_section_svg(segs, axis, value, canvas=canvas)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(svg, encoding="utf-8")
    return {
        "ok": True,
        "axis": _AXIS_NAME[axis],
        "value": value,
        "segment_count": len(segs),
        "svg": str(out_path),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _nice_bar(total_range: float) -> float:
    for v in (1, 2, 5, 10, 20, 50, 100, 200):
        if total_range / v <= 6:
            return float(v)
    return 200.0


def _empty_svg(canvas: int, title: str) -> str:
    mid = canvas // 2
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas}" height="{canvas}">'
        f'<rect width="{canvas}" height="{canvas}" fill="white" rx="3"/>'
        f'<text x="{mid}" y="18" text-anchor="middle" font-size="11" '
        f'font-weight="600" fill="#333" font-family="sans-serif">{title}</text>'
        f'<text x="{mid}" y="{mid}" text-anchor="middle" font-size="13" '
        f'fill="#bbb" font-family="sans-serif">no intersections at this section</text>'
        f'</svg>'
    )
