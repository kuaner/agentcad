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


def _box_source(name: str) -> str:
    return (
        "from build123d import *\n"
        "with BuildPart() as bp:\n"
        "    Box(10, 10, 10)\n"
        "result = bp.part\n"
        "metadata = {\n"
        "    'schema': 'agentcad.part.metadata.v1',\n"
        "    'units': 'mm',\n"
        f"    'model': '{name}',\n"
        "    'interfaces': {\n"
        "        'body': {\n"
        "            'box': {\n"
        "                'type': 'box',\n"
        "                'x_range': [-5, 5],\n"
        "                'y_range': [-5, 5],\n"
        "                'z_range': [-5, 5],\n"
        "            }\n"
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
    assert Path(result["artifacts"]["assembly_stl"]).exists()
    preview_page = Path(result["artifacts"]["preview_page"])
    assert preview_page.exists()
    preview_html = preview_page.read_text(encoding="utf-8")
    assert "three.module.js" in preview_html
    assert "STLLoader" in preview_html
    assert '"kind": "assembly"' in preview_html
    assert 'id="show-all"' in preview_html
    assert 'id="prev-part"' in preview_html
    assert "soloComponent" in preview_html
    assert '"validation": "assembly_validation.json"' in preview_html
    assert '"observability": "assembly_observability.json"' in preview_html
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
    out_dir = tmp_path / "assemblies" / "scaled" / "outputs"
    assert (out_dir / "assembly_validation.json").exists()
    assert (out_dir / "assembly_observability.json").exists()


def test_assembly_validate_blocks_unclassified_component_pair(tmp_path):
    project = _project_with_pin_socket(tmp_path, ignore_pair=False)
    result = validate_assembly(project, "pin_socket")
    assert result["ok"] is False
    pair_check = next(check for check in result["checks"] if check["type"] == "component_pair_classified")
    assert pair_check["ok"] is False


def _project_with_box_pair(tmp_path: Path, separation: float, checks: list[dict]) -> Path:
    init_workspace(tmp_path)
    _scaffold_model(tmp_path, "box_a", _box_source("box_a"))
    _scaffold_model(tmp_path, "box_b", _box_source("box_b"))
    root = tmp_path / "assemblies" / "box_pair"
    root.mkdir(parents=True, exist_ok=True)
    (root / "assembly.json").write_text(
        json.dumps(
            {
                "schema": "agentcad.assembly.v1",
                "name": "box_pair",
                "units": "mm",
                "components": [
                    {"id": "a", "model": "box_a", "transform": {"translation": [0, 0, 0]}},
                    {"id": "b", "model": "box_b", "transform": {"translation": [separation, 0, 0]}},
                ],
                "mates": [],
                "checks": checks,
                "ignore_pairs": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return tmp_path


def test_interference_free_uses_mesh_narrow_phase_for_overlapping_boxes(tmp_path):
    project = _project_with_box_pair(
        tmp_path,
        separation=6.0,
        checks=[{"id": "boxes_do_not_interfere", "type": "interference_free", "components": ["a", "b"], "tolerance_mm": 0.05}],
    )
    result = validate_assembly(project, "box_pair")

    assert result["ok"] is False
    check = next(check for check in result["checks"] if check["name"] == "boxes_do_not_interfere")
    assert check["method"] == "mesh_narrow_phase_v1"
    assert check["mesh_penetration_mm"] > 0.05
    assert check["narrow_phase"]["inside_sample_count"] > 0


def test_inter_model_min_clearance_uses_metadata_shape_refs_and_section_count(tmp_path):
    project = _project_with_box_pair(
        tmp_path,
        separation=12.0,
        checks=[
            {
                "id": "box_gap",
                "type": "inter_model_min_clearance",
                "a": "a.interfaces.body.box",
                "b": "b.interfaces.body.box",
                "min_mm": 1.5,
            },
            {
                "id": "mid_section_has_two_boxes",
                "type": "assembly_section_component_count",
                "z": 0,
                "expected": 2,
            },
        ],
    )
    result = validate_assembly(project, "box_pair")

    assert result["ok"] is True
    clearance = next(check for check in result["checks"] if check["name"] == "box_gap")
    assert clearance["method"] == "shape_descriptor"
    assert clearance["actual_mm"] == 2.0
    section = next(check for check in result["checks"] if check["name"] == "mid_section_has_two_boxes")
    assert section["actual"] == 2


def test_assembly_validate_reports_missing_required_field(tmp_path):
    project = _project_with_pin_socket(tmp_path)
    contract_path = project / "assemblies" / "pin_socket" / "assembly.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    del contract["mates"][0]["max_axis_angle_deg"]
    contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")

    result = validate_assembly(project, "pin_socket")

    assert result["ok"] is False
    assert result["error"]["type"] == "RequiredFieldMissing"
    assert (project / "assemblies" / "pin_socket" / "outputs" / "assembly_validation.json").exists()
    assert (project / "assemblies" / "pin_socket" / "outputs" / "assembly_observability.json").exists()


def test_assembly_validate_rejects_malformed_cylinder_center(tmp_path):
    project = _project_with_pin_socket(tmp_path)
    _write_part(
        project / "models" / "pin",
        _pin_source().replace("'center': [0, 0]", "'center': {'x': 0, 'y': 0}"),
    )

    result = validate_assembly(project, "pin_socket")

    assert result["ok"] is False
    assert result["error"]["type"] == "CylinderDescriptorInvalid"
    assert (project / "assemblies" / "pin_socket" / "outputs" / "assembly_geometry.json").exists()


def test_assembly_validate_rejects_component_ids_that_are_not_mjcf_safe(tmp_path):
    init_workspace(tmp_path)
    root = tmp_path / "assemblies" / "bad_ids"
    root.mkdir(parents=True)
    (root / "assembly.json").write_text(
        json.dumps(
            {
                "schema": "agentcad.assembly.v1",
                "name": "bad_ids",
                "units": "mm",
                "components": [
                    {"id": "bad id", "model": "missing", "transform": {"translation": [0, 0, 0]}},
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = validate_assembly(tmp_path, "bad_ids")

    assert result["ok"] is False
    assert result["error"]["type"] == "ComponentIdInvalid"


def test_assembly_metadata_schema_checks_invalid_interface(tmp_path):
    """Assembly validation reports metadata_schema checks for invalid interfaces."""
    project = _project_with_pin_socket(tmp_path)
    # First run validation normally (build generates valid metadata).
    result = validate_assembly(project, "pin_socket")
    assert result["ok"] is True
    # Now corrupt the pin metadata after build: interface with missing kind.
    pin_metadata = project / "models" / "pin" / "metadata.json"
    pin_metadata.write_text(json.dumps({
        "schema": "agentcad.part.metadata.v1",
        "interfaces": {
            "pin": {},  # missing kind
        },
    }), encoding="utf-8")
    # Re-validate: build is cached (won't overwrite), but metadata is now invalid.
    # The reference resolution should fail and produce a metadata_schema check.
    result2 = validate_assembly(project, "pin_socket")
    # The reference to pin.interfaces.pin.axis won't resolve because
    # the interface has no kind/axis, so the assembly should fail.
    assert result2["ok"] is False
