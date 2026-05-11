from __future__ import annotations

import base64
import html
import http.server
import json
import os
import socketserver
import webbrowser
from functools import lru_cache
from pathlib import Path
from . import templates
from .jsonio import read_json
from .workspace import model_dir, normalize_model_name, outputs_dir, outputs_dir_for_variant

THREE_VERSION = "0.164.1"


def write_model_preview(
    project: Path,
    name: str,
    *,
    validation_payload: dict | None = None,
    geometry_payload: dict | None = None,
    variant: str | None = None,
    static: bool = False,
) -> dict:
    safe = normalize_model_name(name)
    out_dir = outputs_dir_for_variant(project, safe, variant)
    preview_path = out_dir / "preview.html"
    stl_path = out_dir / f"{safe}.stl"
    if not stl_path.exists():
        return _failure("preview", "STLMissing", f"missing STL artifact: {stl_path}", preview_path)

    geometry = geometry_payload if geometry_payload is not None else read_json(out_dir / "geometry.json", default={}) or {}
    validation = validation_payload if validation_payload is not None else read_json(out_dir / "validation.json", default={}) or {}
    review = read_json(out_dir / "review.json", default={}) or {}
    design = read_json(model_dir(project, safe) / "design.json", default={}) or {}
    metadata = read_json(model_dir(project, safe) / "metadata.json", default={}) or {}
    bbox = ((geometry or {}).get("geometry") or {}).get("bbox")

    component: dict = {
        "id": safe,
        "model": safe,
        "matrix": _identity_matrix(),
        "worldBbox": bbox,
        "mesh": ((geometry or {}).get("geometry") or {}).get("mesh"),
        "artifacts": _model_artifact_links(project, safe, out_dir),
    }
    if static:
        component["stlBase64"] = _file_b64(stl_path)
    else:
        component["stlUrl"] = _rel_link(stl_path, out_dir)

    data = {
        "schema": "agentcad.preview.v1",
        "kind": "model",
        "title": safe,
        "units": "mm",
        "status": {
            "ok": bool(validation.get("ok")),
            "stage": validation.get("stage") or "preview",
        },
        "components": [component],
        "geometry": {
            "bbox": bbox,
            "mesh": ((geometry or {}).get("geometry") or {}).get("mesh"),
            "mass_properties": ((geometry or {}).get("geometry") or {}).get("mass_properties"),
            "structure": (geometry or {}).get("structure"),
        },
        "checks": validation.get("checks") or [],
        "warnings": validation.get("warnings") or [],
        "review": {
            "ok": bool(review.get("ok")) if review else None,
            "checklist": review.get("checklist") or [],
            "must_view": review.get("must_view") or [],
            "relations": review.get("relations") or [],
        },
        "design": {
            "intent": design.get("intent"),
            "features": design.get("features") or [],
        },
        "metadata": metadata,
        "svgs": _collect_svg_assets(out_dir, static=static),
        "artifacts": _model_artifact_links(project, safe, out_dir),
        "runtime": _runtime_caps(mjcf=False, static=static),
    }
    if static:
        data["artifactsContent"] = _artifact_contents(_model_artifact_paths(project, safe, out_dir))
    return _write_preview_file(preview_path, data, title=f"AgentCAD Preview - {safe}")


def write_assembly_preview(
    project: Path,
    name: str,
    *,
    validation_payload: dict | None = None,
    geometry_payload: dict | None = None,
    static: bool = False,
) -> dict:
    safe = normalize_model_name(name)
    root = project / "assemblies" / safe
    out_dir = root / "outputs"
    preview_path = out_dir / "preview.html"
    geometry = geometry_payload if geometry_payload is not None else read_json(out_dir / "assembly_geometry.json", default={}) or {}
    validation = validation_payload if validation_payload is not None else read_json(out_dir / "assembly_validation.json", default={}) or {}
    observability = read_json(out_dir / "assembly_observability.json", default={}) or {}
    contract = read_json(root / "assembly.json", default={}) or {}

    components = []
    for cid, component in sorted((geometry.get("components") or {}).items()):
        stl_path = Path((component.get("paths") or {}).get("stl", ""))
        if not stl_path.exists():
            return _failure("assembly_preview", "STLMissing", f"missing component STL artifact: {stl_path}", preview_path)
        entry: dict = {
            "id": cid,
            "model": component.get("model"),
            "matrix": ((component.get("transform") or {}).get("matrix") or _identity_matrix()),
            "worldBbox": component.get("world_bbox"),
            "localBbox": component.get("local_bbox"),
            "mesh": component.get("mesh"),
            "build": component.get("build"),
            "artifacts": _component_artifact_links(component, out_dir),
        }
        if static:
            entry["stlBase64"] = _file_b64(stl_path)
        else:
            entry["stlUrl"] = _rel_link(stl_path, out_dir)
        components.append(entry)

    mjcf_path = out_dir / f"{safe}.mjcf.xml"
    data = {
        "schema": "agentcad.preview.v1",
        "kind": "assembly",
        "title": safe,
        "units": geometry.get("units") or contract.get("units") or "mm",
        "status": {
            "ok": bool(validation.get("ok")),
            "stage": validation.get("stage") or "assembly_preview",
        },
        "intent": contract.get("intent"),
        "components": components,
        "geometry": geometry.get("assembly_geometry") or {},
        "references": geometry.get("references") or {},
        "checks": validation.get("checks") or [],
        "mates": geometry.get("mate_residuals") or validation.get("mate_residuals") or [],
        "pairwise": geometry.get("pairwise") or [],
        "observability": {
            "failed_checks": ((observability.get("checks") or {}).get("failed") if observability else []),
        },
        "svgs": _collect_svg_assets(out_dir, static=static),
        "artifacts": _assembly_artifact_links(root, out_dir),
        "runtime": _runtime_caps(mjcf=mjcf_path.exists(), static=static),
    }
    if static:
        data["artifactsContent"] = _artifact_contents(_assembly_artifact_paths(root, out_dir))
    return _write_preview_file(preview_path, data, title=f"AgentCAD Assembly Preview - {safe}")


def serve_preview(preview_path: Path, *, port: int = 0) -> None:
    directory = str(preview_path.parent.resolve())
    handler = _make_handler(directory)
    with _ReusableThreadedServer(("", port), handler) as httpd:
        actual_port = httpd.server_address[1]
        url = f"http://localhost:{actual_port}/{preview_path.name}"
        print(f"Serving preview at {url}  (Ctrl+C to stop)")
        webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


def open_preview(preview_path: Path) -> None:
    webbrowser.open(preview_path.resolve().as_uri())


class _ReusableThreadedServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True


def _make_handler(directory: str):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)

        def log_message(self, format, *args):
            pass
    return Handler


def _write_preview_file(path: Path, data: dict, title: str) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=True).replace("</", "<\\/")
    path.write_text(_html(title, payload), encoding="utf-8")
    return {
        "ok": True,
        "stage": "preview" if data.get("kind") == "model" else "assembly_preview",
        "kind": data.get("kind"),
        "name": data.get("title"),
        "artifacts": {"preview_page": str(path)},
        "message": "interactive preview generated",
    }


def _failure(stage: str, error_type: str, message: str, path: Path) -> dict:
    return {
        "ok": False,
        "stage": stage,
        "error": {"type": error_type, "message": message},
        "artifacts": {"preview_page": str(path)},
    }


def _runtime_caps(*, mjcf: bool, static: bool) -> dict:
    return {
        "three": {"enabled": True, "source": f"jsdelivr three@{THREE_VERSION}"},
        "stl": {"enabled": True, "mode": "embedded-base64" if static else "fetch-relative-url"},
        "mjcf": {"enabled": mjcf, "mode": "browser-xml-summary-and-agentcad-roundtrip"},
        "occt": {"enabled": False, "mode": "external-viewer-compatible-step-artifact"},
        "mujoco": {"enabled": False, "mjcf_present": mjcf, "mode": "external-viewer-compatible-mjcf-artifact"},
    }


def _file_b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _collect_svg_assets(out_dir: Path, *, static: bool = False) -> list[dict]:
    paths = sorted(out_dir.glob("preview.*.svg")) + sorted(out_dir.glob("section.*.svg"))
    seen: set[Path] = set()
    rows = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        item: dict = {"label": path.stem, "path": _rel_link(path, out_dir)}
        if static:
            item["svgBase64"] = _file_b64(path)
        rows.append(item)
    return rows


def _model_artifact_links(project: Path, name: str, out_dir: Path) -> dict[str, str]:
    return {key: _rel_link(path, out_dir) for key, path in _model_artifact_paths(project, name, out_dir).items()}


def _model_artifact_paths(project: Path, name: str, out_dir: Path) -> dict[str, Path]:
    candidates = {
        "design": model_dir(project, name) / "design.json",
        "metadata": model_dir(project, name) / "metadata.json",
        "build": out_dir / "build.json",
        "geometry": out_dir / "geometry.json",
        "validation": out_dir / "validation.json",
        "observability": out_dir / "observability.json",
        "review": out_dir / "review.json",
        "step": out_dir / f"{name}.step",
        "stl": out_dir / f"{name}.stl",
    }
    return {key: path for key, path in candidates.items() if path.exists()}


def _component_artifact_links(component: dict, out_dir: Path) -> dict[str, str]:
    rows = {}
    for key, value in (component.get("paths") or {}).items():
        path = Path(value)
        if path.exists():
            rows[key] = _rel_link(path, out_dir)
    return rows


def _assembly_artifact_links(root: Path, out_dir: Path) -> dict[str, str]:
    return {key: _rel_link(path, out_dir) for key, path in _assembly_artifact_paths(root, out_dir).items()}


def _assembly_artifact_paths(root: Path, out_dir: Path) -> dict[str, Path]:
    candidates = {
        "assembly": root / "assembly.json",
        "geometry": out_dir / "assembly_geometry.json",
        "validation": out_dir / "assembly_validation.json",
        "observability": out_dir / "assembly_observability.json",
        "review": out_dir / "assembly_review.json",
        "mjcf": out_dir / f"{root.name}.mjcf.xml",
        "assembly_stl": out_dir / f"{root.name}.stl",
    }
    return {key: path for key, path in candidates.items() if path.exists()}


def _artifact_contents(paths: dict[str, Path]) -> dict:
    out: dict = {}
    for key, path in paths.items():
        suffix = path.suffix.lower()
        if suffix == ".json":
            try:
                out[key] = {"format": "json", "data": json.loads(path.read_text(encoding="utf-8"))}
            except (OSError, ValueError):
                continue
        elif suffix == ".xml":
            try:
                out[key] = {"format": "xml", "text": path.read_text(encoding="utf-8")}
            except OSError:
                continue
    return out


def _rel_link(path: Path, base: Path) -> str:
    try:
        return os.path.relpath(path, start=base)
    except ValueError:
        return str(path)


def _identity_matrix() -> list[list[float]]:
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


@lru_cache(maxsize=1)
def _template() -> str:
    return (templates._templates_dir() / "preview" / "preview.html").read_text(encoding="utf-8")


def _html(title: str, payload: str) -> str:
    return (
        _template()
        .replace("{{title}}", html.escape(title))
        .replace("{{three_version}}", THREE_VERSION)
        .replace("{{payload}}", payload)
    )
