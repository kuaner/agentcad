from __future__ import annotations

import html
from pathlib import Path

from .jsonio import write_json
from .stl import Vec3, cross, dot, normalize, read_stl, sub, triangle_normal
from .workspace import outputs_dir


VIEW_DIRS: dict[str, Vec3] = {
    "front": (0.0, -1.0, 0.0),
    "top": (0.0, 0.0, 1.0),
    "side": (1.0, 0.0, 0.0),
    "iso": (1.0, -1.0, 0.75),
}


def render_model(project: Path, name: str, view: str = "iso") -> dict:
    actual_view = view if view in VIEW_DIRS else "iso"
    out_dir = outputs_dir(project, name)
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
        svg = triangles_to_svg(triangles, title=f"{name} {actual_view}", view=actual_view)
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


def triangles_to_svg(triangles, title: str = "preview", view: str = "iso", width: int = 960, height: int = 720) -> str:
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
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            "<rect width=\"100%\" height=\"100%\" fill=\"#f7f8fb\"/>",
            f"<title>{escaped}</title>",
            *polygons,
            "</svg>",
            "",
        ]
    )


def _empty_svg(width: int, height: int, title: str) -> str:
    escaped = html.escape(title)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f"<title>{escaped}</title>"
        '<rect width="100%" height="100%" fill="#f7f8fb"/>'
        '<text x="50%" y="50%" text-anchor="middle" fill="#596273">No geometry</text>'
        "</svg>\n"
    )
