from __future__ import annotations

from pathlib import Path

from ..jsonio import write_json
from ..stl import Triangle
from .analysis import analyze_section_segments
from .extraction import section_segments
from .types import Segment2D, _AXIS_NAME, _PLANE_LABELS

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
    analysis_path: Path | None = None,
    write_analysis: bool = True,
) -> dict:
    """Extract section, render SVG, and write measured sidecar JSON."""
    segs = section_segments(triangles, axis, value)
    svg = render_section_svg(segs, axis, value, canvas=canvas)
    analysis = analyze_section_segments(segs, axis, value)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(svg, encoding="utf-8")
    analysis_payload = {
        "stage": "section_analysis",
        "svg": str(out_path),
        **analysis,
    }
    analysis_json = None
    if write_analysis:
        analysis_path = analysis_path or out_path.with_suffix(".json")
        write_json(analysis_path, analysis_payload)
        analysis_json = str(analysis_path)
    return {
        "ok": True,
        "axis": _AXIS_NAME[axis],
        "value": value,
        "segment_count": len(segs),
        "svg": str(out_path),
        "analysis": analysis_payload,
        "analysis_json": analysis_json,
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
