"""Tests for P2.1 metadata interface schema validation.

Validates that interface entries in metadata.json are correctly validated:
unknown kinds, malformed axes, missing required fields, screw spec resolution,
cylinder descriptor validation, and anchor validation.
"""
from __future__ import annotations

from agentcad.metadata import (
    validate_part_metadata_dict,
    VALID_INTERFACE_KINDS,
)
from agentcad.contract import SchemaIssue


# ── valid metadata ────────────────────────────────────────────────────────


class TestValidMetadata:
    def test_empty_metadata_passes(self):
        issues = validate_part_metadata_dict({})
        assert issues == []

    def test_valid_schema_version(self):
        issues = validate_part_metadata_dict({"schema": "agentcad.part.metadata.v1"})
        assert issues == []

    def test_no_schema_version_passes(self):
        issues = validate_part_metadata_dict({})
        assert not any(i.path == "schema" for i in issues)

    def test_valid_cylindrical_male_interface(self):
        metadata = {
            "interfaces": {
                "duct_socket": {
                    "kind": "cylindrical_male",
                    "axis": {"point": [0, 0, 0], "direction": [0, 0, 1]},
                    "outer_cylinder": {
                        "type": "cylinder",
                        "axis": "z",
                        "center": [0, 0],
                        "radius": 20,
                        "z_range": [0, 10],
                    },
                },
            },
        }
        issues = validate_part_metadata_dict(metadata)
        error_issues = [i for i in issues if i.severity == "error"]
        assert error_issues == []

    def test_valid_cylindrical_female_interface(self):
        metadata = {
            "interfaces": {
                "duct_lid": {
                    "kind": "cylindrical_female",
                    "axis": {"point": [0, 0, 0], "direction": [0, 0, 1]},
                    "inner_cylinder": {
                        "type": "cylinder",
                        "axis": "z",
                        "center": [0, 0],
                        "radius": 19.5,
                        "z_range": [0, 10],
                    },
                },
            },
        }
        issues = validate_part_metadata_dict(metadata)
        error_issues = [i for i in issues if i.severity == "error"]
        assert error_issues == []

    def test_valid_screw_axis_interface(self):
        metadata = {
            "interfaces": {
                "m3_install": {
                    "kind": "screw_axis",
                    "axis": {"point": [10, 0, 4], "direction": [0, 0, 1]},
                    "clearance_diameter": 8,
                    "screw": "M3_cap",
                },
            },
        }
        issues = validate_part_metadata_dict(metadata)
        error_issues = [i for i in issues if i.severity == "error"]
        assert error_issues == []

    def test_valid_planar_interface(self):
        """Planar interfaces don't require axis."""
        metadata = {
            "interfaces": {
                "base_face": {
                    "kind": "planar",
                },
            },
        }
        issues = validate_part_metadata_dict(metadata)
        error_issues = [i for i in issues if i.severity == "error"]
        assert error_issues == []


# ── invalid metadata ────────────────────────────────────────────────────────


class TestInvalidMetadata:
    def test_invalid_schema_version(self):
        issues = validate_part_metadata_dict({"schema": "v2"})
        assert any(i.path == "schema" and i.severity == "error" for i in issues)

    def test_interfaces_not_dict(self):
        issues = validate_part_metadata_dict({"interfaces": "bad"})
        assert any(i.path == "interfaces" for i in issues)

    def test_interface_not_dict(self):
        issues = validate_part_metadata_dict({"interfaces": {"x": 5}})
        assert any("interfaces.x" in i.path for i in issues)

    def test_interface_missing_kind(self):
        issues = validate_part_metadata_dict({"interfaces": {"x": {}}})
        assert any("interfaces.x.kind" in i.path for i in issues)

    def test_interface_unknown_kind(self):
        issues = validate_part_metadata_dict({"interfaces": {"x": {"kind": "teleporter"}}})
        assert any("interfaces.x.kind" in i.path for i in issues)

    def test_cylindrical_missing_axis(self):
        issues = validate_part_metadata_dict({
            "interfaces": {"x": {"kind": "cylindrical_male"}},
        })
        assert any("interfaces.x.axis" in i.path for i in issues)

    def test_cylindrical_missing_cylinder_descriptors(self):
        issues = validate_part_metadata_dict({
            "interfaces": {"x": {
                "kind": "cylindrical_male",
                "axis": {"point": [0, 0, 0], "direction": [0, 0, 1]},
            }},
        })
        assert any("interfaces.x" in i.path and ("outer_cylinder" in i.message or "inner_cylinder" in i.message) for i in issues)

    def test_cylinder_descriptor_wrong_type(self):
        issues = validate_part_metadata_dict({
            "interfaces": {"x": {
                "kind": "cylindrical_male",
                "axis": {"point": [0, 0, 0], "direction": [0, 0, 1]},
                "outer_cylinder": {"type": "box"},
            }},
        })
        assert any("outer_cylinder.type" in i.path for i in issues)

    def test_cylinder_descriptor_bad_radius(self):
        issues = validate_part_metadata_dict({
            "interfaces": {"x": {
                "kind": "cylindrical_male",
                "axis": {"point": [0, 0, 0], "direction": [0, 0, 1]},
                "outer_cylinder": {"type": "cylinder", "axis": "z", "center": [0, 0], "radius": -5, "z_range": [0, 10]},
            }},
        })
        assert any("radius" in i.path and "positive" in i.message for i in issues)

    def test_cylinder_descriptor_missing_range(self):
        issues = validate_part_metadata_dict({
            "interfaces": {"x": {
                "kind": "cylindrical_male",
                "axis": {"point": [0, 0, 0], "direction": [0, 0, 1]},
                "outer_cylinder": {"type": "cylinder", "axis": "z", "center": [0, 0], "radius": 20},
            }},
        })
        assert any("z_range" in i.path or "z_range" in i.message for i in issues)

    def test_axis_missing_point(self):
        issues = validate_part_metadata_dict({
            "interfaces": {"x": {
                "kind": "cylindrical_male",
                "axis": {"direction": [0, 0, 1]},
                "outer_cylinder": {"type": "cylinder", "axis": "z", "radius": 20, "z_range": [0, 10]},
            }},
        })
        assert any("axis.point" in i.path for i in issues)

    def test_axis_zero_direction(self):
        issues = validate_part_metadata_dict({
            "interfaces": {"x": {
                "kind": "cylindrical_male",
                "axis": {"point": [0, 0, 0], "direction": [0, 0, 0]},
                "outer_cylinder": {"type": "cylinder", "axis": "z", "radius": 20, "z_range": [0, 10]},
            }},
        })
        assert any("direction" in i.path and "zero" in i.message for i in issues)

    def test_screw_axis_missing_clearance_diameter(self):
        issues = validate_part_metadata_dict({
            "interfaces": {"x": {
                "kind": "screw_axis",
                "axis": {"point": [0, 0, 0], "direction": [0, 0, 1]},
            }},
        })
        assert any("clearance_diameter" in i.path for i in issues)

    def test_screw_axis_bad_spec_is_warning(self):
        """Unknown screw spec is a warning, not an error."""
        issues = validate_part_metadata_dict({
            "interfaces": {"x": {
                "kind": "screw_axis",
                "axis": {"point": [0, 0, 0], "direction": [0, 0, 1]},
                "clearance_diameter": 8,
                "screw": "FAKE_SPEC",
            }},
        })
        screw_issues = [i for i in issues if "screw" in i.path]
        assert len(screw_issues) == 1
        assert screw_issues[0].severity == "warning"


# ── anchors ────────────────────────────────────────────────────────────────


class TestAnchors:
    def test_valid_anchor(self):
        issues = validate_part_metadata_dict({
            "anchors": {
                "origin": {"point": [0, 0, 0]},
            },
        })
        assert issues == []

    def test_anchor_with_direction(self):
        issues = validate_part_metadata_dict({
            "anchors": {
                "mount": {"point": [5, 5, 5], "direction": [0, 0, 1]},
            },
        })
        assert issues == []

    def test_anchor_missing_point(self):
        issues = validate_part_metadata_dict({
            "anchors": {"x": {}},
        })
        assert any("anchors.x.point" in i.path for i in issues)

    def test_anchor_bad_point(self):
        issues = validate_part_metadata_dict({
            "anchors": {"x": {"point": "bad"}},
        })
        assert any("anchors.x.point" in i.path for i in issues)

    def test_anchor_bad_direction(self):
        issues = validate_part_metadata_dict({
            "anchors": {"x": {"point": [0, 0, 0], "direction": "bad"}},
        })
        assert any("anchors.x.direction" in i.path for i in issues)

    def test_anchors_not_dict(self):
        issues = validate_part_metadata_dict({"anchors": "bad"})
        assert any(i.path == "anchors" for i in issues)


# ── non-dict metadata ────────────────────────────────────────────────────────


class TestNonDictMetadata:
    def test_non_dict_metadata_fails(self):
        issues = validate_part_metadata_dict("not a dict")
        assert len(issues) == 1
        assert issues[0].path == ""

    def test_list_metadata_fails(self):
        issues = validate_part_metadata_dict([])
        assert len(issues) == 1


# ── valid interface kinds ──────────────────────────────────────────────────


class TestInterfaceKinds:
    def test_all_kinds_accepted(self):
        for kind in VALID_INTERFACE_KINDS:
            iface = {"kind": kind}
            if kind != "planar":
                iface["axis"] = {"point": [0, 0, 0], "direction": [0, 0, 1]}
            if kind in ("cylindrical_male", "cylindrical_female"):
                iface["outer_cylinder"] = {
                    "type": "cylinder", "axis": "z", "center": [0, 0], "radius": 10, "z_range": [0, 5],
                }
            if kind == "screw_axis":
                iface["clearance_diameter"] = 8
            issues = validate_part_metadata_dict({"interfaces": {"test": iface}})
            error_issues = [i for i in issues if i.severity == "error"]
            assert error_issues == [], f"kind={kind} should be valid but got errors: {error_issues}"


# ── ContractBuilder interface emission ────────────────────────────────────────


class TestContractBuilderInterface:
    def test_add_interface(self):
        from agentcad.features import ContractBuilder
        b = ContractBuilder(intent="test")
        b.add_interface("duct_socket", {
            "kind": "cylindrical_male",
            "axis": {"point": [0, 0, 0], "direction": [0, 0, 1]},
            "outer_cylinder": {
                "type": "cylinder", "axis": "z", "center": [0, 0], "radius": 20, "z_range": [0, 10],
            },
        })
        assert "duct_socket" in b.interfaces
        assert b.interfaces["duct_socket"]["kind"] == "cylindrical_male"

    def test_duplicate_interface_name_raises(self):
        from agentcad.features import ContractBuilder
        b = ContractBuilder(intent="test")
        b.add_interface("x", {"kind": "planar"})
        import pytest
        with pytest.raises(ValueError, match="duplicate interface"):
            b.add_interface("x", {"kind": "planar"})

    def test_to_metadata_includes_interfaces(self):
        from agentcad.features import ContractBuilder
        b = ContractBuilder(intent="test")
        b.add_interface("duct", {
            "kind": "cylindrical_male",
            "axis": {"point": [0, 0, 0], "direction": [0, 0, 1]},
            "outer_cylinder": {
                "type": "cylinder", "axis": "z", "center": [0, 0], "radius": 20, "z_range": [0, 10],
            },
        })
        metadata = b.to_metadata()
        assert metadata["schema"] == "agentcad.part.metadata.v1"
        assert "duct" in metadata["interfaces"]

    def test_to_metadata_empty_interfaces(self):
        from agentcad.features import ContractBuilder
        b = ContractBuilder(intent="test")
        metadata = b.to_metadata()
        assert "interfaces" not in metadata