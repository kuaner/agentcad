from __future__ import annotations

import html
from pathlib import Path

from .jsonio import read_json, write_json
from .stl import Vec3, cross, dot, normalize, read_stl, sub, triangle_normal
from .workspace import model_dir, outputs_dir, outputs_dir_for_variant


VIEW_DIRS: dict[str, Vec3] = {
    "front": (0.0, -1.0, 0.0),
    "top": (0.0, 0.0, 1.0),
    "side": (1.0, 0.0, 0.0),
    "iso": (1.0, -1.0, 0.75),
    # dir.z < 0 → back face (Z=0) has greater depth → rendered in front.
    # Slight +Y tilt avoids the world-up singularity and keeps the back
    # panel facing the viewer so camera/port cutouts are clearly visible.
    "back": (0.0, 0.5, -1.0),
}


def render_models_multi(project: Path, name: str, views: list[str], variant: str | None = None) -> dict:
    """Render multiple views and return a combined result dict.

    Returns ``ok=True`` only when every requested view succeeds. The ``artifacts``
    dict maps ``preview_<view>`` → path for each successfully rendered view.
    """
    results = []
    artifacts: dict[str, str] = {}
    for v in views:
        r = render_model(project, name, view=v, variant=variant)
        results.append(r)
        if r.get("ok"):
            actual_view = v if v in VIEW_DIRS else "iso"
            preview_path = (r.get("artifacts") or {}).get("preview")
            if preview_path:
                artifacts[f"preview_{actual_view}"] = preview_path
    all_ok = all(r.get("ok") for r in results)
    return {
        "ok": all_ok,
        "stage": "render",
        "model": name,
        "views": views,
        "artifacts": artifacts,
        "results": results,
        "message": "all views rendered" if all_ok else "some views failed",
    }


def render_model(project: Path, name: str, view: str = "iso", variant: str | None = None) -> dict:
    actual_view = view if view in VIEW_DIRS else "iso"
    out_dir = outputs_dir_for_variant(project, name, variant)
    stl_path = out_dir / f"{name}.stl"
    svg_path = out_dir / f"preview.{actual_view}.svg"
    report_path = out_dir / f"render.{actual_view}.json"
    if not stl_path.exists():
        payload = {
            "ok": False,
            "stage": "render",
            "model": name,
            "error": {"type": "ArtifactMissing", "message": f"missing STL artifact: {stl_path}", "file": str(stl_path)},
        }
        write_json(report_path, payload)
        return payload

    try:
        triangles = read_stl(stl_path)
        geom = read_json(out_dir / "geometry.json", default={}) or {}
        bbox = (geom.get("geometry") or {}).get("bbox")
        svg = triangles_to_svg(triangles, title=f"{name} {actual_view}", view=actual_view, bbox=bbox)
        svg_path.write_text(svg, encoding="utf-8")
    except Exception as exc:
        payload = {
            "ok": False,
            "stage": "render",
            "model": name,
            "error": {"type": type(exc).__name__, "message": str(exc), "file": str(stl_path)},
        }
        write_json(report_path, payload)
        return payload

    payload = {
        "ok": True,
        "stage": "render",
        "model": name,
        "view": actual_view,
        "artifacts": {"preview": str(svg_path), "render": str(report_path)},
        "message": "preview rendered",
    }
    write_json(report_path, payload)
    return payload


def triangles_to_svg(
    triangles,
    title: str = "preview",
    view: str = "iso",
    width: int = 960,
    height: int = 720,
    bbox: dict | None = None,
) -> str:
    direction = normalize(VIEW_DIRS.get(view, VIEW_DIRS["iso"]))
    world_up: Vec3 = (0.0, 0.0, 1.0)
    raw_right = cross(world_up, direction)
    if dot(raw_right, raw_right) < 1e-8:
        right = (1.0, 0.0, 0.0)
    else:
        right = normalize(raw_right)
    up = normalize(cross(direction, right))
    light = normalize((-0.4, -0.6, 1.0))

    projected = []
    min_u = min_v = float("inf")
    max_u = max_v = float("-inf")
    for tri in triangles:
        pts = []
        depths = []
        for p in tri:
            u = dot(p, right)
            v = dot(p, up)
            d = dot(p, direction)
            pts.append((u, v))
            depths.append(d)
            min_u = min(min_u, u)
            max_u = max(max_u, u)
            min_v = min(min_v, v)
            max_v = max(max_v, v)
        normal = triangle_normal(tri)
        shade = max(0.2, min(0.95, 0.45 + 0.45 * dot(normal, light)))
        projected.append((sum(depths) / 3.0, pts, shade))

    if not projected:
        return _empty_svg(width, height, title)

    margin = 32
    span_u = max(max_u - min_u, 1e-6)
    span_v = max(max_v - min_v, 1e-6)
    scale = min((width - 2 * margin) / span_u, (height - 2 * margin) / span_v)

    def screen(pt):
        u, v = pt
        x = margin + (u - min_u) * scale
        y = height - margin - (v - min_v) * scale
        return x, y

    polygons = []
    for _, pts, shade in sorted(projected, key=lambda item: item[0]):
        color = int(255 * shade)
        fill = f"rgb({color},{color},{color})"
        screen_pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in (screen(p) for p in pts))
        polygons.append(f'<polygon points="{screen_pts}" fill="{fill}" stroke="#30343b" stroke-width="0.6"/>')

    escaped = html.escape(title)
    annotations = _dimension_annotations(bbox, right, up, min_u, max_u, min_v, max_v, scale, margin, width, height) if bbox else ""
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            "<rect width=\"100%\" height=\"100%\" fill=\"#f7f8fb\"/>",
            f"<title>{escaped}</title>",
            *polygons,
            annotations,
            "</svg>",
            "",
        ]
    )

def _axis_label(vec: Vec3) -> str:
    labels = ("X", "Y", "Z")
    abs_vals = [abs(c) for c in vec]
    return labels[abs_vals.index(max(abs_vals))]


def _nice_bar(total_range: float) -> float:
    for v in (1, 2, 5, 10, 20, 50, 100, 200, 500):
        if total_range / v <= 6:
            return float(v)
    return 500.0


def _dimension_annotations(
    bbox: dict,
    right: Vec3,
    up: Vec3,
    min_u: float,
    max_u: float,
    min_v: float,
    max_v: float,
    scale: float,
    margin: float,
    width: int,
    height: int,
) -> str:
    size = bbox.get("size") or []
    if len(size) < 3:
        return ""

    u_axis = _axis_label(right)
    v_axis = _axis_label(up)
    axis_idx = {"X": 0, "Y": 1, "Z": 2}

    u_dim = size[axis_idx[u_axis]]
    v_dim = size[axis_idx[v_axis]]

    u_cx = margin + (max_u - min_u) * scale / 2
    v_cy = height - margin - (max_v - min_v) * scale / 2

    u_left = margin
    u_right = margin + (max_u - min_u) * scale
    v_top = height - margin - (max_v - min_v) * scale
    v_bottom = height - margin

    elements: list[str] = []

    # Horizontal dimension line (below the rendering area)
    dy = 14
    y = v_bottom + dy
    elements.append(f'<line x1="{u_left:.1f}" y1="{y:.1f}" x2="{u_right:.1f}" y2="{y:.1f}" stroke="#999" stroke-width="0.8"/>')
    elements.append(f'<line x1="{u_left:.1f}" y1="{y - 3:.1f}" x2="{u_left:.1f}" y2="{y + 3:.1f}" stroke="#999" stroke-width="0.8"/>')
    elements.append(f'<line x1="{u_right:.1f}" y1="{y - 3:.1f}" x2="{u_right:.1f}" y2="{y + 3:.1f}" stroke="#999" stroke-width="0.8"/>')
    elements.append(f'<text x="{u_cx:.1f}" y="{y + 11}" text-anchor="middle" font-size="9" fill="#777" font-family="monospace">{u_dim:.1f} mm ({u_axis})</text>')

    # Vertical dimension line (left of the rendering area)
    dx = 14
    x = u_left - dx
    elements.append(f'<line x1="{x:.1f}" y1="{v_top:.1f}" x2="{x:.1f}" y2="{v_bottom:.1f}" stroke="#999" stroke-width="0.8"/>')
    elements.append(f'<line x1="{x - 3:.1f}" y1="{v_top:.1f}" x2="{x + 3:.1f}" y2="{v_top:.1f}" stroke="#999" stroke-width="0.8"/>')
    elements.append(f'<line x1="{x - 3:.1f}" y1="{v_bottom:.1f}" x2="{x + 3:.1f}" y2="{v_bottom:.1f}" stroke="#999" stroke-width="0.8"/>')
    elements.append(f'<text x="{x - 4:.1f}" y="{v_cy:.1f}" text-anchor="middle" font-size="9" fill="#777" font-family="monospace" transform="rotate(-90 {x - 4:.1f} {v_cy:.1f})">{v_dim:.1f} mm ({v_axis})</text>')

    # Scale bar (bottom-right corner)
    mm_range = max(max_u - min_u, max_v - min_v)
    bar_mm = _nice_bar(mm_range)
    bar_px = bar_mm * scale
    bx = u_right - bar_px
    by = v_bottom + 28
    elements.append(f'<line x1="{bx:.1f}" y1="{by:.1f}" x2="{bx + bar_px:.1f}" y2="{by:.1f}" stroke="#999" stroke-width="1.5"/>')
    elements.append(f'<text x="{bx + bar_px / 2:.1f}" y="{by + 11:.1f}" text-anchor="middle" font-size="9" fill="#999" font-family="sans-serif">{bar_mm:.0f} mm</text>')

    return f'<g id="annotations">{"".join(elements)}</g>'


def _empty_svg(width: int, height: int, title: str) -> str:
    escaped = html.escape(title)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f"<title>{escaped}</title>"
        '<rect width="100%" height="100%" fill="#f7f8fb"/>'
        '<text x="50%" y="50%" text-anchor="middle" fill="#596273">No geometry</text>'
        "</svg>\n"
    )
