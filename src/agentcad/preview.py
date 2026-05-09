from __future__ import annotations

import base64
import html
import json
import os
from pathlib import Path
from typing import Any

from .jsonio import read_json
from .workspace import model_dir, normalize_model_name, outputs_dir

THREE_VERSION = "0.164.1"


def write_model_preview(
    project: Path,
    name: str,
    *,
    validation_payload: dict | None = None,
    geometry_payload: dict | None = None,
) -> dict:
    safe = normalize_model_name(name)
    out_dir = outputs_dir(project, safe)
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

    data = {
        "schema": "agentcad.preview.v1",
        "kind": "model",
        "title": safe,
        "units": "mm",
        "status": {
            "ok": bool(validation.get("ok")),
            "stage": validation.get("stage") or "preview",
        },
        "components": [
            {
                "id": safe,
                "model": safe,
                "stlBase64": _file_b64(stl_path),
                "matrix": _identity_matrix(),
                "worldBbox": bbox,
                "mesh": ((geometry or {}).get("geometry") or {}).get("mesh"),
                "artifacts": _model_artifact_links(project, safe, out_dir),
            }
        ],
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
        "svgs": _collect_svg_assets(out_dir),
        "artifacts": _model_artifact_links(project, safe, out_dir),
        "runtime": _runtime_caps(mjcf=False),
    }
    return _write_preview_file(preview_path, data, title=f"AgentCAD Preview - {safe}")


def write_assembly_preview(
    project: Path,
    name: str,
    *,
    validation_payload: dict | None = None,
    geometry_payload: dict | None = None,
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
        components.append(
            {
                "id": cid,
                "model": component.get("model"),
                "stlBase64": _file_b64(stl_path),
                "matrix": ((component.get("transform") or {}).get("matrix") or _identity_matrix()),
                "worldBbox": component.get("world_bbox"),
                "localBbox": component.get("local_bbox"),
                "mesh": component.get("mesh"),
                "build": component.get("build"),
                "artifacts": _component_artifact_links(component, out_dir),
            }
        )

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
        "svgs": _collect_svg_assets(out_dir),
        "mjcf": {
            "path": _rel_link(mjcf_path, out_dir) if mjcf_path.exists() else None,
            "xml": mjcf_path.read_text(encoding="utf-8") if mjcf_path.exists() else None,
        },
        "artifacts": _assembly_artifact_links(root, out_dir),
        "runtime": _runtime_caps(mjcf=mjcf_path.exists()),
    }
    return _write_preview_file(preview_path, data, title=f"AgentCAD Assembly Preview - {safe}")


def _write_preview_file(path: Path, data: dict, title: str) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
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


def _runtime_caps(*, mjcf: bool) -> dict:
    return {
        "three": {"enabled": True, "source": f"jsdelivr three@{THREE_VERSION}"},
        "stl": {"enabled": True, "mode": "embedded-base64"},
        "mjcf": {"enabled": mjcf, "mode": "browser-xml-summary-and-agentcad-roundtrip"},
        "occt": {"enabled": False, "mode": "external-viewer-compatible-step-artifact"},
        "mujoco": {"enabled": False, "mjcf_present": mjcf, "mode": "external-viewer-compatible-mjcf-artifact"},
    }


def _file_b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _collect_svg_assets(out_dir: Path) -> list[dict]:
    paths = sorted(out_dir.glob("preview.*.svg")) + sorted(out_dir.glob("section.*.svg"))
    seen: set[Path] = set()
    rows = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        rows.append(
            {
                "label": path.stem,
                "path": _rel_link(path, out_dir),
                "svgBase64": _file_b64(path),
            }
        )
    return rows


def _model_artifact_links(project: Path, name: str, out_dir: Path) -> dict[str, str]:
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
    return {key: _rel_link(path, out_dir) for key, path in candidates.items() if path.exists()}


def _component_artifact_links(component: dict, out_dir: Path) -> dict[str, str]:
    rows = {}
    for key, value in (component.get("paths") or {}).items():
        path = Path(value)
        if path.exists():
            rows[key] = _rel_link(path, out_dir)
    return rows


def _assembly_artifact_links(root: Path, out_dir: Path) -> dict[str, str]:
    candidates = {
        "assembly": root / "assembly.json",
        "geometry": out_dir / "assembly_geometry.json",
        "validation": out_dir / "assembly_validation.json",
        "observability": out_dir / "assembly_observability.json",
        "review": out_dir / "assembly_review.json",
        "mjcf": out_dir / f"{root.name}.mjcf.xml",
        "assembly_stl": out_dir / f"{root.name}.stl",
    }
    return {key: _rel_link(path, out_dir) for key, path in candidates.items() if path.exists()}


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


def _html(title: str, payload: str) -> str:
    escaped_title = html.escape(title)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <title>{escaped_title}</title>
  <style>
    :root {{
      color-scheme: light;
      --paper: #f4f1ea;
      --panel: #fbfaf6;
      --ink: #171b1f;
      --muted: #667078;
      --line: #d8d2c6;
      --line-strong: #a9a195;
      --green: #1f7a4d;
      --red: #b8322a;
      --amber: #a96d16;
      --blue: #286d9b;
      --tool: #2d3439;
      --tool-2: #414b52;
      --shadow: 0 18px 48px rgba(32, 28, 20, .18);
    }}
    * {{ box-sizing: border-box; }}
    html {{
      height: 100%;
      overflow: hidden;
    }}
    body {{
      margin: 0;
      height: 100%;
      min-height: 100vh;
      overflow: hidden;
      background: var(--paper);
      color: var(--ink);
      font: 14px/1.45 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    button, input {{ font: inherit; }}
    .app {{ height: 100vh; min-height: 0; display: grid; grid-template-rows: auto minmax(0, 1fr); }}
    .topbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      padding: 12px 18px;
      background: #20272c;
      color: #f7f4ec;
      border-bottom: 1px solid #11171b;
    }}
    .brand {{ display: flex; align-items: baseline; gap: 12px; min-width: 0; }}
    .brand strong {{ font-size: 15px; letter-spacing: 0; }}
    .brand span {{ color: #c7d0d6; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .status-pill {{
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      padding: 4px 10px;
      border: 1px solid rgba(255,255,255,.18);
      background: rgba(255,255,255,.08);
      color: #f8f5ee;
      font-size: 12px;
    }}
    .status-pill.ok {{ background: rgba(31, 122, 77, .34); }}
    .status-pill.fail {{ background: rgba(184, 50, 42, .34); }}
    .shell {{
      display: grid;
      grid-template-columns: minmax(280px, 360px) minmax(360px, 1fr) minmax(300px, 420px);
      height: 100%;
      min-height: 0;
      overflow: hidden;
    }}
    aside {{
      min-height: 0;
      overflow: auto;
      background: var(--panel);
      border-right: 1px solid var(--line);
    }}
    aside.right {{ border-right: 0; border-left: 1px solid var(--line); }}
    .stage {{ position: relative; min-height: 0; overflow: hidden; background: #e8e4da; display: grid; grid-template-rows: auto minmax(0, 1fr); }}
    .toolbar {{
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
      padding: 10px;
      border-bottom: 1px solid var(--line);
      background: rgba(251,250,246,.88);
    }}
    .tool-btn {{
      min-height: 32px;
      padding: 5px 10px;
      border: 1px solid var(--line-strong);
      background: #fffdfa;
      color: var(--tool);
      cursor: pointer;
    }}
    .tool-btn.active {{ background: var(--tool); color: #fffdfa; border-color: var(--tool); }}
    .slider {{ display: inline-flex; align-items: center; gap: 8px; margin-left: auto; color: var(--muted); font-size: 12px; }}
    .slider input {{ width: 160px; }}
    #viewer {{ position: relative; min-height: 0; width: 100%; height: 100%; overflow: hidden; contain: layout size paint; }}
    #viewer canvas {{ display: block; width: 100% !important; height: 100% !important; }}
    .section {{ padding: 16px 16px 18px; border-bottom: 1px solid var(--line); }}
    .section h2 {{ margin: 0 0 10px; font-size: 12px; line-height: 1.2; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); }}
    .kv {{ display: grid; grid-template-columns: 116px 1fr; gap: 6px 10px; }}
    .kv div:nth-child(odd) {{ color: var(--muted); }}
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }}
    .component-row {{
      display: grid;
      grid-template-columns: auto minmax(0, 1fr) auto;
      gap: 10px;
      align-items: center;
      padding: 8px 0;
      border-bottom: 1px solid color-mix(in srgb, var(--line), transparent 35%);
    }}
    .swatch {{ width: 14px; height: 14px; border: 1px solid rgba(0,0,0,.18); }}
    .component-row label {{ display: flex; align-items: center; gap: 8px; min-width: 0; }}
    .component-row input {{ width: 16px; height: 16px; }}
    .component-main {{ min-width: 0; }}
    .component-title {{ display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .component-meta {{ display: block; color: var(--muted); font-size: 12px; margin-top: 2px; }}
    .component-actions {{ display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px; }}
    .mini-btn {{
      min-height: 26px;
      padding: 3px 8px;
      border: 1px solid var(--line-strong);
      background: #fffdfa;
      color: var(--tool);
      cursor: pointer;
      font-size: 12px;
    }}
    .mini-btn.active {{ background: var(--tool-2); color: #fffdfa; border-color: var(--tool-2); }}
    .check-list {{ display: grid; gap: 8px; }}
    .check {{
      border-left: 4px solid var(--line-strong);
      padding: 7px 9px;
      background: #fffdfa;
      box-shadow: 0 1px 0 rgba(0,0,0,.03);
    }}
    .check.ok {{ border-left-color: var(--green); }}
    .check.fail {{ border-left-color: var(--red); }}
    .check-name {{ display: flex; justify-content: space-between; gap: 10px; font-weight: 650; }}
    .check-type {{ margin-top: 2px; color: var(--muted); font-size: 12px; }}
    .metric-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }}
    .metric {{ background: #fffdfa; border: 1px solid var(--line); padding: 8px; }}
    .metric b {{ display: block; font-size: 18px; line-height: 1.1; }}
    .metric span {{ display: block; color: var(--muted); font-size: 11px; margin-top: 3px; }}
    .svg-grid {{ display: grid; grid-template-columns: 1fr; gap: 10px; }}
    .svg-card {{ background: #fffdfa; border: 1px solid var(--line); padding: 8px; }}
    .svg-card img {{ display: block; width: 100%; height: auto; border: 1px solid #e8e1d6; background: white; }}
    .svg-card a, .links a {{ color: var(--blue); text-decoration: none; }}
    .svg-card a:hover, .links a:hover {{ text-decoration: underline; }}
    pre {{
      margin: 0;
      max-height: 260px;
      overflow: auto;
      padding: 10px;
      background: #20272c;
      color: #f7f4ec;
      font-size: 11px;
      line-height: 1.45;
    }}
    .empty {{ color: var(--muted); }}
    @media (max-width: 1080px) {{
      .shell {{ grid-template-columns: 1fr; grid-template-rows: auto minmax(520px, 70vh) auto; }}
      html, body {{ overflow: auto; }}
      .app {{ height: auto; min-height: 100vh; }}
      .shell {{ height: auto; overflow: visible; }}
      aside, aside.right {{ border: 0; border-bottom: 1px solid var(--line); }}
      aside.left {{ order: 2; }}
      .stage {{ order: 1; }}
      aside.right {{ order: 3; }}
    }}
  </style>
</head>
<body>
  <div class="app">
    <header class="topbar">
      <div class="brand"><strong>AgentCAD Preview</strong><span id="title"></span></div>
      <div id="status" class="status-pill"></div>
    </header>
    <main class="shell">
      <aside class="left">
        <section class="section">
          <h2>Summary</h2>
          <div id="summary" class="kv"></div>
        </section>
        <section class="section">
          <h2>Components</h2>
          <div id="components"></div>
        </section>
        <section class="section">
          <h2>Checks</h2>
          <div id="checks" class="check-list"></div>
        </section>
      </aside>
      <section class="stage">
        <div class="toolbar">
          <button class="tool-btn active" data-mode="solid" type="button">Solid</button>
          <button class="tool-btn" data-mode="xray" type="button">X-Ray</button>
          <button class="tool-btn" data-mode="wire" type="button">Wire</button>
          <button class="tool-btn" id="fit" type="button">Fit</button>
          <button class="tool-btn" id="view-iso" type="button">Iso</button>
          <button class="tool-btn" id="view-top" type="button">Top</button>
          <button class="tool-btn" id="view-front" type="button">Front</button>
          <button class="tool-btn" id="assembled" type="button">Assembled</button>
          <button class="tool-btn" id="exploded" type="button">Exploded</button>
          <button class="tool-btn" id="show-all" type="button">All Parts</button>
          <button class="tool-btn" id="prev-part" type="button">Prev Part</button>
          <button class="tool-btn" id="next-part" type="button">Next Part</button>
          <div class="slider"><span>Explode</span><input id="explode" type="range" min="0" max="1" value="0" step="0.01"></div>
        </div>
        <div id="viewer"></div>
      </section>
      <aside class="right">
        <section class="section">
          <h2>Measurements</h2>
          <div id="metrics" class="metric-grid"></div>
        </section>
        <section class="section">
          <h2>Mates And Pairs</h2>
          <div id="relations"></div>
        </section>
        <section class="section">
          <h2>SVG Evidence</h2>
          <div id="svgs" class="svg-grid"></div>
        </section>
        <section class="section">
          <h2>Artifacts</h2>
          <div id="links" class="links"></div>
        </section>
        <section class="section" id="mjcf-section">
          <h2>MJCF</h2>
          <div id="mjcf-summary" class="kv"></div>
          <pre id="mjcf"></pre>
        </section>
      </aside>
    </main>
  </div>
  <script type="importmap">
    {{
      "imports": {{
        "three": "https://cdn.jsdelivr.net/npm/three@{THREE_VERSION}/build/three.module.js",
        "three/addons/": "https://cdn.jsdelivr.net/npm/three@{THREE_VERSION}/examples/jsm/"
      }}
    }}
  </script>
  <script>window.AGENTCAD_PREVIEW = {payload};</script>
  <script type="module">
    import * as THREE from "three";
    import {{ OrbitControls }} from "three/addons/controls/OrbitControls.js";
    import {{ STLLoader }} from "three/addons/loaders/STLLoader.js";

    const data = window.AGENTCAD_PREVIEW;
    const colors = [0x2f6f95, 0xb46a2b, 0x4d7f48, 0x8d5a97, 0xa14b4b, 0x5f7f94, 0x7d713b];
    const host = document.getElementById("viewer");
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xe8e4da);
    const camera = new THREE.PerspectiveCamera(42, 1, 0.01, 10000);
    const renderer = new THREE.WebGLRenderer({{ antialias: true, alpha: false }});
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    host.appendChild(renderer.domElement);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    const root = new THREE.Group();
    scene.add(root);
    scene.add(new THREE.HemisphereLight(0xffffff, 0x7a756b, 2.6));
    const key = new THREE.DirectionalLight(0xffffff, 2.8);
    key.position.set(90, -120, 170);
    key.castShadow = true;
    scene.add(key);
    const fill = new THREE.DirectionalLight(0xd7edf8, 1.4);
    fill.position.set(-140, 90, 80);
    scene.add(fill);
    const grid = new THREE.GridHelper(160, 32, 0x9b9488, 0xc9c1b6);
    grid.rotation.x = Math.PI / 2;
    scene.add(grid);
    scene.add(new THREE.AxesHelper(36));

    const loader = new STLLoader();
    const entries = [];
    let currentMode = "solid";
    let activeSoloId = null;

    function decodeBase64(b64) {{
      const binary = atob(b64);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      return bytes.buffer;
    }}
    function matrixFromRows(rows) {{
      const m = new THREE.Matrix4();
      const r = rows || [[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]];
      m.set(r[0][0], r[0][1], r[0][2], r[0][3], r[1][0], r[1][1], r[1][2], r[1][3], r[2][0], r[2][1], r[2][2], r[2][3], r[3][0], r[3][1], r[3][2], r[3][3]);
      return m;
    }}
    function bboxCenter(bbox) {{
      const c = bbox && bbox.center ? bbox.center : [0, 0, 0];
      return new THREE.Vector3(c[0], c[1], c[2]);
    }}
    function materialFor(index) {{
      return new THREE.MeshStandardMaterial({{
        color: colors[index % colors.length],
        metalness: 0.08,
        roughness: 0.58,
        transparent: false,
        opacity: 1,
        side: THREE.DoubleSide
      }});
    }}
    function buildScene() {{
      const assemblyCenter = bboxCenter((data.geometry || {{}}).bbox || data.geometry);
      data.components.forEach((component, index) => {{
        const geometry = loader.parse(decodeBase64(component.stlBase64));
        geometry.computeVertexNormals();
        const mesh = new THREE.Mesh(geometry, materialFor(index));
        mesh.castShadow = true;
        mesh.receiveShadow = true;
        mesh.applyMatrix4(matrixFromRows(component.matrix));
        const group = new THREE.Group();
        group.name = component.id;
        group.add(mesh);
        const center = bboxCenter(component.worldBbox);
        let dir = center.clone().sub(assemblyCenter);
        if (dir.length() < 0.001) dir = new THREE.Vector3(Math.cos(index * 2.399), Math.sin(index * 2.399), 0.25);
        dir.normalize();
        group.userData.explodeDir = dir;
        group.userData.baseVisible = true;
        root.add(group);
        entries.push({{ component, group, mesh, material: mesh.material, color: colors[index % colors.length] }});
      }});
    }}
    function setMode(mode) {{
      currentMode = mode;
      entries.forEach((entry) => {{
        entry.material.wireframe = mode === "wire";
        entry.material.transparent = mode === "xray";
        entry.material.opacity = mode === "xray" ? 0.38 : 1;
        entry.material.depthWrite = mode !== "xray";
      }});
      document.querySelectorAll("[data-mode]").forEach((btn) => btn.classList.toggle("active", btn.dataset.mode === mode));
    }}
    function setExplode(value) {{
      const box = new THREE.Box3().setFromObject(root);
      const size = box.getSize(new THREE.Vector3()).length() || 1;
      entries.forEach((entry) => entry.group.position.copy(entry.group.userData.explodeDir.clone().multiplyScalar(value * size * 0.42)));
    }}
    function visibleBox() {{
      const box = new THREE.Box3();
      let hasVisible = false;
      entries.forEach((entry) => {{
        if (!entry.group.visible) return;
        const entryBox = new THREE.Box3().setFromObject(entry.group);
        if (!entryBox.isEmpty()) {{
          box.union(entryBox);
          hasVisible = true;
        }}
      }});
      return hasVisible ? box : new THREE.Box3().setFromObject(root);
    }}
    function fitCamera(view = "iso", object = null) {{
      const box = object ? new THREE.Box3().setFromObject(object) : visibleBox();
      if (box.isEmpty()) return;
      const center = box.getCenter(new THREE.Vector3());
      const sphere = box.getBoundingSphere(new THREE.Sphere());
      const radius = Math.max(sphere.radius, 1);
      const dirs = {{
        iso: new THREE.Vector3(1.2, -1.4, 0.9),
        top: new THREE.Vector3(0, 0, 1),
        front: new THREE.Vector3(0, -1, 0.1)
      }};
      const dir = (dirs[view] || dirs.iso).clone().normalize();
      camera.position.copy(center.clone().add(dir.multiplyScalar(radius * 2.6)));
      camera.near = Math.max(0.01, radius / 1000);
      camera.far = Math.max(1000, radius * 12);
      camera.updateProjectionMatrix();
      controls.target.copy(center);
      controls.update();
    }}
    function syncComponentControls() {{
      entries.forEach((entry) => {{
        if (entry.checkbox) entry.checkbox.checked = entry.group.visible;
        if (entry.soloButton) entry.soloButton.classList.toggle("active", activeSoloId === entry.component.id);
      }});
    }}
    function showAllParts() {{
      activeSoloId = null;
      entries.forEach((entry) => {{ entry.group.visible = true; }});
      syncComponentControls();
      fitCamera("iso");
    }}
    function soloComponent(entry) {{
      activeSoloId = entry.component.id;
      entries.forEach((candidate) => {{ candidate.group.visible = candidate === entry; }});
      syncComponentControls();
      fitCamera("iso", entry.group);
    }}
    function soloByOffset(delta) {{
      if (!entries.length) return;
      let index = entries.findIndex((entry) => entry.component.id === activeSoloId);
      if (index < 0) index = delta >= 0 ? -1 : 0;
      const next = (index + delta + entries.length) % entries.length;
      soloComponent(entries[next]);
    }}
    function focusComponent(entry) {{
      fitCamera("iso", entry.group);
    }}
    function resize() {{
      const rect = host.getBoundingClientRect();
      const width = Math.min(Math.max(Math.floor(rect.width || host.clientWidth || 1), 1), 4096);
      const height = Math.min(Math.max(Math.floor(rect.height || host.clientHeight || 1), 1), 4096);
      renderer.setSize(width, height, false);
      renderer.domElement.style.width = "100%";
      renderer.domElement.style.height = "100%";
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    }}
    function renderLoop() {{
      controls.update();
      renderer.render(scene, camera);
      requestAnimationFrame(renderLoop);
    }}

    function text(value) {{ return value === undefined || value === null ? "n/a" : String(value); }}
    function mm(value) {{ return Number.isFinite(Number(value)) ? `${{Number(value).toFixed(2)}} mm` : "n/a"; }}
    function addKv(host, key, value) {{
      const k = document.createElement("div");
      const v = document.createElement("div");
      k.textContent = key;
      v.textContent = value;
      v.className = "mono";
      host.append(k, v);
    }}
    function renderUi() {{
      document.getElementById("title").textContent = `${{data.kind}} / ${{data.title}}`;
      const status = document.getElementById("status");
      status.textContent = data.status.ok ? "PASS" : "FAIL";
      status.classList.add(data.status.ok ? "ok" : "fail");
      const summary = document.getElementById("summary");
      addKv(summary, "Kind", data.kind);
      addKv(summary, "Units", data.units || "mm");
      addKv(summary, "Components", text(data.components.length));
      addKv(summary, "Checks", text((data.checks || []).length));
      if (data.intent) addKv(summary, "Intent", data.intent);

      const components = document.getElementById("components");
      entries.forEach((entry, index) => {{
        const row = document.createElement("div");
        row.className = "component-row";
        const swatch = document.createElement("span");
        swatch.className = "swatch";
        swatch.style.background = `#${{entry.color.toString(16).padStart(6, "0")}}`;
        const label = document.createElement("label");
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.checked = true;
        checkbox.addEventListener("change", () => {{
          activeSoloId = null;
          entry.group.visible = checkbox.checked;
          syncComponentControls();
          fitCamera("iso");
        }});
        entry.checkbox = checkbox;
        const main = document.createElement("span");
        main.className = "component-main";
        const name = document.createElement("span");
        name.className = "component-title";
        name.textContent = `${{entry.component.id}} / ${{entry.component.model || entry.component.id}}`;
        const mesh = entry.component.mesh || {{}};
        const tris = document.createElement("span");
        tris.className = "component-meta mono";
        tris.textContent = mesh.triangles ? `${{mesh.triangles}} tri` : "";
        main.append(name, tris);
        label.append(checkbox, main);
        const actions = document.createElement("div");
        actions.className = "component-actions";
        const focus = document.createElement("button");
        focus.type = "button";
        focus.className = "mini-btn";
        focus.textContent = "Focus";
        focus.addEventListener("click", () => focusComponent(entry));
        const solo = document.createElement("button");
        solo.type = "button";
        solo.className = "mini-btn";
        solo.textContent = "Solo";
        solo.addEventListener("click", () => soloComponent(entry));
        entry.soloButton = solo;
        actions.append(focus, solo);
        row.append(swatch, label, actions);
        components.append(row);
      }});

      const checks = document.getElementById("checks");
      const orderedChecks = [...(data.checks || [])].sort((a, b) => Number(Boolean(a.ok)) - Number(Boolean(b.ok)));
      if (!orderedChecks.length) checks.innerHTML = '<div class="empty">No checks found.</div>';
      orderedChecks.forEach((check) => {{
        const row = document.createElement("div");
        row.className = `check ${{check.ok ? "ok" : "fail"}}`;
        const head = document.createElement("div");
        head.className = "check-name";
        const name = document.createElement("span");
        name.textContent = check.name || check.id || "check";
        const result = document.createElement("span");
        result.textContent = check.ok ? "ok" : "fail";
        head.append(name, result);
        const type = document.createElement("div");
        type.className = "check-type";
        const actual = check.actual_mm !== undefined ? ` / actual ${{mm(check.actual_mm)}}` : "";
        type.textContent = `${{check.type || "check"}}${{actual}}`;
        row.append(head, type);
        checks.append(row);
      }});

      const metrics = document.getElementById("metrics");
      const bbox = (data.geometry || {{}}).bbox || data.geometry || {{}};
      const size = bbox.size || [];
      [["X", size[0]], ["Y", size[1]], ["Z", size[2]]].forEach(([label, value]) => {{
        const m = document.createElement("div");
        m.className = "metric";
        m.innerHTML = `<b>${{mm(value)}}</b><span>${{label}} envelope</span>`;
        metrics.append(m);
      }});
      const mesh = (data.geometry || {{}}).mesh || {{}};
      if (mesh.triangles) {{
        const m = document.createElement("div");
        m.className = "metric";
        m.innerHTML = `<b>${{mesh.triangles}}</b><span>triangles</span>`;
        metrics.append(m);
      }}
      if ((data.geometry || {{}}).triangle_count) {{
        const m = document.createElement("div");
        m.className = "metric";
        m.innerHTML = `<b>${{data.geometry.triangle_count}}</b><span>triangles</span>`;
        metrics.append(m);
      }}

      const relations = document.getElementById("relations");
      const relRows = [...(data.mates || []), ...(data.pairwise || []), ...((data.review || {{}}).relations || [])];
      if (!relRows.length) relations.innerHTML = '<div class="empty">No mate or pair rows.</div>';
      relRows.forEach((row) => {{
        const box = document.createElement("div");
        box.className = `check ${{row.ok === false || row.interferes ? "fail" : "ok"}}`;
        const comps = row.components ? row.components.join(" + ") : [row.a, row.b].filter(Boolean).join(" + ");
        const details = [];
        if (row.angle_deg !== undefined) details.push(`angle ${{Number(row.angle_deg).toFixed(4)}} deg`);
        if (row.radial_offset_mm !== undefined) details.push(`offset ${{mm(row.radial_offset_mm)}}`);
        if (row.actual_mm !== undefined) details.push(`actual ${{mm(row.actual_mm)}}`);
        if (row.aabb_clearance_mm !== undefined) details.push(`AABB clearance ${{mm(row.aabb_clearance_mm)}}`);
        box.innerHTML = `<div class="check-name"><span>${{row.name || row.type || comps || "relation"}}</span><span>${{row.ok === false || row.interferes ? "fail" : "ok"}}</span></div><div class="check-type">${{comps}} ${{details.join(" / ")}}</div>`;
        relations.append(box);
      }});

      const svgs = document.getElementById("svgs");
      if (!(data.svgs || []).length) svgs.innerHTML = '<div class="empty">No SVG evidence found.</div>';
      (data.svgs || []).forEach((item) => {{
        const card = document.createElement("div");
        card.className = "svg-card";
        card.innerHTML = `<a href="${{item.path}}">${{item.label}}</a><img src="data:image/svg+xml;base64,${{item.svgBase64}}" alt="${{item.label}}">`;
        svgs.append(card);
      }});

      const links = document.getElementById("links");
      Object.entries(data.artifacts || {{}}).forEach(([key, value]) => {{
        const row = document.createElement("div");
        row.innerHTML = `<a href="${{value}}">${{key}}</a>`;
        links.append(row);
      }});
      if (!links.children.length) links.innerHTML = '<div class="empty">No artifact links.</div>';

      const mjcfSection = document.getElementById("mjcf-section");
      const mjcfXml = data.mjcf && data.mjcf.xml;
      if (!mjcfXml) {{
        mjcfSection.style.display = "none";
      }} else {{
        const parser = new DOMParser();
        const doc = parser.parseFromString(mjcfXml, "application/xml");
        const host = document.getElementById("mjcf-summary");
        addKv(host, "Bodies", text(doc.querySelectorAll("worldbody > body").length));
        addKv(host, "Meshes", text(doc.querySelectorAll("asset > mesh").length));
        addKv(host, "Sites", text(doc.querySelectorAll("site").length));
        document.getElementById("mjcf").textContent = mjcfXml;
      }}
    }}

    buildScene();
    renderUi();
    setMode("solid");
    resize();
    fitCamera("iso");
    renderLoop();
    new ResizeObserver(() => {{ resize(); }}).observe(host);
    document.querySelectorAll("[data-mode]").forEach((btn) => btn.addEventListener("click", () => setMode(btn.dataset.mode)));
    document.getElementById("explode").addEventListener("input", (event) => setExplode(Number(event.target.value)));
    document.getElementById("fit").addEventListener("click", () => fitCamera("iso"));
    document.getElementById("view-iso").addEventListener("click", () => fitCamera("iso"));
    document.getElementById("view-top").addEventListener("click", () => fitCamera("top"));
    document.getElementById("view-front").addEventListener("click", () => fitCamera("front"));
    document.getElementById("assembled").addEventListener("click", () => {{
      const input = document.getElementById("explode");
      input.value = "0";
      setExplode(0);
      fitCamera("iso");
    }});
    document.getElementById("exploded").addEventListener("click", () => {{
      const input = document.getElementById("explode");
      input.value = "1";
      setExplode(1);
      fitCamera("iso");
    }});
    document.getElementById("show-all").addEventListener("click", () => showAllParts());
    document.getElementById("prev-part").addEventListener("click", () => soloByOffset(-1));
    document.getElementById("next-part").addEventListener("click", () => soloByOffset(1));
  </script>
</body>
</html>
"""
