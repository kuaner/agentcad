from __future__ import annotations

import json
from pathlib import Path

from agentcad.assembly import init_assembly, list_assemblies, validate_assembly
from agentcad.workspace import init_workspace, new_model


def _write_part(model_dir: Path, source: str) -> None:
    (model_dir / "part.py").write_text(source, encoding="utf-8")


def _scaffold_model(project: Path, name: str, source: str) -> None:
    new_model(project, name)
    _write_part(project / "models" / name, source)


def _pin_source() -> str:
    return (
        "from build123d import *\n"
        "with BuildPart() as bp:\n"
        "    Cylinder(radius=5.0, height=10.0, align=(Align.CENTER, Align.CENTER, Align.MIN))\n"
        "result = bp.part\n"
        "metadata = {\n"
        "    'schema': 'agentcad.part.metadata.v1',\n"
        "    'units': 'mm',\n"
        "    'model': 'pin',\n"
        "    'interfaces': {\n"
        "        'pin': {\n"
        "            'axis': {'point': [0, 0, 0], 'direction': [0, 0, 1]},\n"
        "            'outer_cylinder': {\n"
        "                'type': 'cylinder', 'axis': 'z', 'center': [0, 0],\n"
        "                'radius_mm': 5.0, 'z_range': [1.0, 9.0],\n"
        "                'surface': 'outer', 'tolerance_mm': 0.25,\n"
        "            },\n"
        "        }\n"
        "    },\n"
        "}\n"
    )


def _socket_source() -> str:
    return (
        "from build123d import *\n"
        "with BuildPart() as bp:\n"
        "    Cylinder(radius=8.0, height=8.0, align=(Align.CENTER, Align.CENTER, Align.MIN))\n"
        "    with Locations((0, 0, -0.2)):\n"
        "        Cylinder(radius=5.3, height=8.4, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)\n"
        "result = bp.part\n"
        "metadata = {\n"
        "    'schema': 'agentcad.part.metadata.v1',\n"
        "    'units': 'mm',\n"
        "    'model': 'socket',\n"
        "    'interfaces': {\n"
        "        'socket': {\n"
        "            'axis': {'point': [0, 0, 0], 'direction': [0, 0, 1]},\n"
        "            'inner_cylinder': {\n"
        "                'type': 'cylinder', 'axis': 'z', 'center': [0, 0],\n"
        "                'radius_mm': 5.3, 'z_range': [1.0, 7.0],\n"
        "                'surface': 'inner', 'tolerance_mm': 0.25,\n"
        "            },\n"
        "        }\n"
        "    },\n"
        "}\n"
    )


def _write_assembly(project: Path, ignore_pair: bool = True) -> None:
    root = project / "assemblies" / "pin_socket"
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "agentcad.assembly.v1",
        "name": "pin_socket",
        "units": "mm",
        "components": [
            {"id": "pin", "model": "pin", "transform": {"translation": [0, 0, 0], "rotation_euler_deg": [0, 0, 0]}},
            {"id": "socket", "model": "socket", "transform": {"translation": [0, 0, 2.5], "rotation_euler_deg": [0, 0, 0]}},
        ],
        "mates": [
            {
                "id": "pin_socket_coaxial",
                "type": "coaxial",
                "a": "pin.interfaces.pin.axis",
                "b": "socket.interfaces.socket.axis",
                "max_axis_angle_deg": 0.1,
                "max_radial_offset_mm": 0.01,
            },
            {
                "id": "pin_socket_engagement",
                "type": "axial_engagement",
                "a": "pin.interfaces.pin.outer_cylinder",
                "b": "socket.interfaces.socket.inner_cylinder",
                "min_mm": 5.0,
            },
        ],
        "checks": [
            {
                "id": "pin_socket_radial_clearance",
                "type": "radial_clearance",
                "inner": "socket.interfaces.socket.inner_cylinder",
                "outer": "pin.interfaces.pin.outer_cylinder",
                "min_mm": 0.2,
                "max_mm": 0.4,
            },
            {
                "id": "assembly_envelope",
                "type": "assembly_bbox_size",
                "expected": [16.0, 16.0, 10.5],
                "tolerance_mm": 0.2,
            },
        ],
        "ignore_pairs": [],
    }
    if ignore_pair:
        payload["ignore_pairs"].append(
            {
                "components": ["pin", "socket"],
                "reason": "fit pair is covered by coaxial, radial clearance, and axial engagement checks",
            }
        )
    (root / "assembly.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _project_with_pin_socket(tmp_path: Path, ignore_pair: bool = True) -> Path:
    init_workspace(tmp_path)
    _scaffold_model(tmp_path, "pin", _pin_source())
    _scaffold_model(tmp_path, "socket", _socket_source())
    _write_assembly(tmp_path, ignore_pair=ignore_pair)
    return tmp_path


def test_assembly_init_and_list(tmp_path):
    init_workspace(tmp_path)
    created = init_assembly(tmp_path, "demo")
    assert created["ok"] is True
    listed = list_assemblies(tmp_path)
    assert listed["ok"] is True
    assert [row["name"] for row in listed["assemblies"]] == ["demo"]


def test_assembly_validate_generates_geometry_previews_and_mjcf(tmp_path):
    project = _project_with_pin_socket(tmp_path)
    result = validate_assembly(project, "pin_socket")
    assert result["ok"] is True
    assert Path(result["artifacts"]["geometry"]).exists()
    assert Path(result["artifacts"]["preview_combined_iso"]).exists()
    assert Path(result["artifacts"]["preview_exploded_iso"]).exists()
    preview_page = Path(result["artifacts"]["preview_page"])
    assert preview_page.exists()
    preview_html = preview_page.read_text(encoding="utf-8")
    assert "three.module.js" in preview_html
    assert "STLLoader" in preview_html
    assert '"kind": "assembly"' in preview_html
    assert 'id="show-all"' in preview_html
    assert 'id="prev-part"' in preview_html
    assert "soloComponent" in preview_html
    assert Path(result["artifacts"]["mjcf"]).exists()
    radial = next(check for check in result["checks"] if check["name"] == "pin_socket_radial_clearance")
    assert 0.2 <= radial["actual_mm"] <= 0.4
    assert any(check["type"] == "mjcf_consistency" and check["ok"] for check in result["checks"])


def test_assembly_validate_rejects_scale(tmp_path):
    init_workspace(tmp_path)
    root = tmp_path / "assemblies" / "scaled"
    root.mkdir(parents=True)
    (root / "assembly.json").write_text(
        json.dumps(
            {
                "schema": "agentcad.assembly.v1",
                "name": "scaled",
                "units": "mm",
                "components": [
                    {"id": "part", "model": "missing", "transform": {"translation": [0, 0, 0], "scale": 2}},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    result = validate_assembly(tmp_path, "scaled")
    assert result["ok"] is False
    assert result["error"]["type"] == "ScaleNotAllowed"


def test_assembly_validate_blocks_unclassified_component_pair(tmp_path):
    project = _project_with_pin_socket(tmp_path, ignore_pair=False)
    result = validate_assembly(project, "pin_socket")
    assert result["ok"] is False
    pair_check = next(check for check in result["checks"] if check["type"] == "component_pair_classified")
    assert pair_check["ok"] is False
