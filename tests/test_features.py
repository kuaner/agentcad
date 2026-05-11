from __future__ import annotations

import json
from pathlib import Path

import pytest

from build123d import (
    Align,
    BuildPart,
    Cylinder,
    Location,
    Mode,
    add,
)

from agentcad.features import ContractBuilder, plate, mounting_pattern, stepped_bore
from agentcad.features.thread import sinusoidal_thread
from agentcad.features.knurl import helical_knurl


# --- Existing thread/knurl tests ---

def test_thread_single_start():
    thread = sinusoidal_thread(radius=20.0, pitch=9.0, height=10.0, n_starts=1)
    assert thread.volume > 0
    assert len(thread.solids()) == 1


def test_thread_three_start():
    thread = sinusoidal_thread(radius=20.0, pitch=9.0, height=10.0, n_starts=3)
    assert thread.volume > 0
    single = sinusoidal_thread(radius=20.0, pitch=9.0, height=10.0, n_starts=1)
    assert thread.volume > single.volume * 2


def test_thread_external_body_union():
    with BuildPart() as body:
        Cylinder(radius=22.0, height=15.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
        thread = sinusoidal_thread(radius=20.0, pitch=9.0, height=10.0, n_starts=3)
        add(thread.moved(Location((0, 0, 5))))
    part = body.part
    assert part.volume > 0
    assert len(part.solids()) == 1


def test_thread_internal_lid_subtract():
    with BuildPart() as lid:
        Cylinder(radius=25.0, height=12.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
        Cylinder(radius=20.2, height=10.0, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
        thread = sinusoidal_thread(radius=20.0, pitch=9.0, height=10.0, n_starts=3)
        add(thread, mode=Mode.SUBTRACT)
    part = lid.part
    assert part.volume > 0


def test_thread_invalid_params():
    with pytest.raises(ValueError):
        sinusoidal_thread(radius=0, pitch=9.0, height=10.0)
    with pytest.raises(ValueError):
        sinusoidal_thread(radius=20.0, pitch=0, height=10.0)
    with pytest.raises(ValueError):
        sinusoidal_thread(radius=20.0, pitch=9.0, height=-5.0)
    with pytest.raises(ValueError):
        sinusoidal_thread(radius=20.0, pitch=9.0, height=10.0, n_starts=0)
    with pytest.raises(ValueError):
        sinusoidal_thread(radius=20.0, pitch=9.0, height=10.0, n_starts=1.5)


def test_knurl_single_direction():
    grooves = helical_knurl(radius=20.0, height=20.0, diamond=False)
    assert len(grooves) > 0
    assert all(g.volume > 0 for g in grooves)


def test_knurl_diamond():
    single = helical_knurl(radius=20.0, height=20.0, diamond=False)
    diamond = helical_knurl(radius=20.0, height=20.0, diamond=True)
    assert len(diamond) > len(single)
    assert all(g.volume > 0 for g in diamond)


def test_knurl_invalid_params():
    with pytest.raises(ValueError):
        helical_knurl(radius=0, height=10.0)
    with pytest.raises(ValueError):
        helical_knurl(radius=20.0, height=-5.0)


# --- ContractBuilder tests ---

class TestContractBuilder:
    def test_empty_builder(self):
        b = ContractBuilder(intent="test part")
        doc = b.to_design()
        assert doc["intent"] == "test part"
        assert doc["features"] == []
        assert doc["checks"] == []

    def test_add_feature_and_checks(self):
        b = ContractBuilder()
        b.add(
            feature={"id": "plate", "description": "a plate"},
            checks=[{"id": "plate_bbox", "type": "bbox_size", "expected": [10, 20, 3]}],
        )
        assert len(b.features) == 1
        assert len(b.checks) == 1
        assert b.features[0]["id"] == "plate"

    def test_duplicate_feature_id_raises(self):
        b = ContractBuilder()
        b.add_feature({"id": "plate", "description": "first"})
        with pytest.raises(ValueError, match="duplicate feature id"):
            b.add_feature({"id": "plate", "description": "second"})

    def test_duplicate_check_id_raises(self):
        b = ContractBuilder()
        b.add_check({"id": "bbox", "type": "bbox_size"})
        with pytest.raises(ValueError, match="duplicate check id"):
            b.add_check({"id": "bbox", "type": "watertight"})

    def test_write_to_creates_design_json(self, tmp_path):
        from agentcad.workspace import init_workspace, new_model

        init_workspace(tmp_path / "proj")
        new_model(tmp_path / "proj", "part")

        b = ContractBuilder(intent="test")
        b.add(
            feature={"id": "test_plate", "description": "plate"},
            checks=[{"id": "test_plate_bbox", "type": "bbox_size", "expected": [10, 10, 3]}],
        )
        result = b.write_to(tmp_path / "proj", "part")
        feat_ids = [f["id"] for f in result["features"]]
        assert "test_plate" in feat_ids

        design_path = tmp_path / "proj" / "models" / "part" / "design.json"
        assert design_path.exists()
        loaded = json.loads(design_path.read_text())
        loaded_ids = [f["id"] for f in loaded["features"]]
        assert "test_plate" in loaded_ids

    def test_write_to_merges_with_existing(self, tmp_path):
        from agentcad.workspace import init_workspace, new_model

        proj = tmp_path / "proj"
        init_workspace(proj)
        new_model(proj, "part")
        design_path = proj / "models" / "part" / "design.json"
        design_path.write_text(json.dumps({
            "schema": "design-spec.v1",
            "features": [{"id": "existing_feat", "description": "old"}],
            "checks": [{"id": "existing_check", "type": "watertight"}],
        }))

        b = ContractBuilder()
        b.add(
            feature={"id": "new_feat", "description": "new"},
            checks=[{"id": "new_check", "type": "bbox_size", "expected": [1, 1, 1]}],
        )
        result = b.write_to(proj, "part")
        feat_ids = [f["id"] for f in result["features"]]
        check_ids = [c["id"] for c in result["checks"]]
        assert "existing_feat" in feat_ids
        assert "new_feat" in feat_ids
        assert "existing_check" in check_ids
        assert "new_check" in check_ids


# --- Plate helper tests ---

class TestPlate:
    def test_returns_part(self):
        p = plate(100, 50, 5)
        assert p.volume > 0

    def test_bbox_dimensions(self):
        p = plate(100, 50, 5)
        bb = p.bounding_box()
        assert bb.max.X - bb.min.X == pytest.approx(100, abs=0.5)
        assert bb.max.Y - bb.min.Y == pytest.approx(50, abs=0.5)
        assert bb.max.Z - bb.min.Z == pytest.approx(5, abs=0.5)

    def test_with_fillet(self):
        p = plate(100, 50, 5, fillet_r=2)
        assert p.volume > 0

    def test_registers_contract(self):
        b = ContractBuilder()
        plate(100, 50, 5, builder=b)
        assert len(b.features) == 1
        assert b.features[0]["id"] == "plate"
        assert len(b.checks) >= 1
        assert b.checks[0]["type"] == "bbox_size"

    def test_custom_feature_id(self):
        b = ContractBuilder()
        plate(100, 50, 5, builder=b, feature_id="base_plate")
        assert b.features[0]["id"] == "base_plate"
        assert b.checks[0]["id"] == "base_plate_bbox"


# --- Mounting pattern tests ---

class TestMountingPattern:
    def test_square_pattern_returns_holes(self):
        holes = mounting_pattern("M3", kind="square", spacing=25)
        assert len(holes.positions) == 4

    def test_rectangular_pattern(self):
        holes = mounting_pattern("M3", kind="rectangular", spacing_x=30, spacing_y=20)
        assert len(holes.positions) == 4

    def test_linear_pattern(self):
        holes = mounting_pattern("M3", kind="linear", spacing=25, count=4)
        assert len(holes.positions) == 4

    def test_registers_checks(self):
        b = ContractBuilder()
        mounting_pattern("M3", kind="square", spacing=25, builder=b)
        assert len(b.features) == 1
        assert b.features[0]["id"] == "mounting_holes"
        # square = 4 holes × (diameter + accessibility) = 8 checks
        assert len(b.checks) == 8

    def test_custom_screw_spec(self):
        b = ContractBuilder()
        mounting_pattern("M4_cap", kind="square", spacing=30, builder=b)
        assert "M4_cap" in b.features[0]["description"]

    def test_linear_pattern_check_count(self):
        b = ContractBuilder()
        mounting_pattern("M3", kind="linear", spacing=20, count=3, builder=b)
        # 3 holes × (diameter + accessibility) = 6 checks
        assert len(b.checks) == 6


# --- Stepped bore tests ---

class TestSteppedBore:
    def test_plain_bore_returns_bore(self):
        bore = stepped_bore("M3", bore_kind="plain", through_depth=10)
        assert bore.through_r > 0

    def test_counterbore_returns_bore(self):
        bore = stepped_bore("M3_cap", bore_kind="counterbore", through_depth=10)
        assert bore.through_r > 0

    def test_plain_registers_one_check(self):
        b = ContractBuilder()
        stepped_bore("M3", bore_kind="plain", through_depth=10, builder=b)
        assert len(b.checks) == 1
        assert b.checks[0]["type"] == "inner_diameter_at_z"

    def test_counterbore_registers_two_checks(self):
        b = ContractBuilder()
        stepped_bore("M3_cap", bore_kind="counterbore", through_depth=10, builder=b)
        assert len(b.checks) == 2
        types = [c["type"] for c in b.checks]
        assert "inner_diameter_at_z" in types


# --- Boss tests ---

class TestBoss:
    def test_returns_part(self):
        from agentcad.features import boss
        b = boss(diameter=10, height=5)
        assert b.volume > 0

    def test_with_hole_check(self):
        from agentcad.features import boss
        builder = ContractBuilder()
        boss(diameter=10, height=5, inner_diameter=4, builder=builder)
        assert len(builder.checks) == 1
        assert builder.checks[0]["type"] == "inner_diameter_at_z"

    def test_without_hole_no_check(self):
        from agentcad.features import boss
        builder = ContractBuilder()
        boss(diameter=10, height=5, builder=builder)
        assert len(builder.checks) == 0
        assert len(builder.features) == 1


# --- Rib tests ---

class TestRib:
    def test_returns_part(self):
        from agentcad.features import rib
        r = rib(length=30, height=10, thickness=3)
        assert r.volume > 0

    def test_direction_y(self):
        from agentcad.features import rib
        r = rib(length=30, height=10, thickness=3, direction="y")
        assert r.volume > 0

    def test_registers_wall_thickness(self):
        from agentcad.features import rib
        builder = ContractBuilder()
        rib(length=30, height=10, thickness=3, builder=builder)
        assert len(builder.checks) == 1
        assert builder.checks[0]["type"] == "min_wall_thickness"

    def test_invalid_direction(self):
        from agentcad.features import rib
        with pytest.raises(ValueError, match="direction"):
            rib(length=30, height=10, thickness=3, direction="z")


# --- Duct socket tests ---

class TestDuctSocket:
    def test_returns_part(self):
        from agentcad.features import duct_socket
        ds = duct_socket(outer_diameter=80, inner_diameter=79.4, length=28)
        assert ds.volume > 0

    def test_registers_id_check(self):
        from agentcad.features import duct_socket
        builder = ContractBuilder()
        duct_socket(outer_diameter=80, inner_diameter=79.4, length=28, builder=builder)
        assert len(builder.checks) == 1
        assert builder.checks[0]["type"] == "inner_diameter_at_z"

    def test_with_lead_in_adds_taper_check(self):
        from agentcad.features import duct_socket
        builder = ContractBuilder()
        duct_socket(outer_diameter=80, inner_diameter=79.4, length=28, lead_in=2.0, builder=builder)
        assert len(builder.checks) == 2
        types = [c["type"] for c in builder.checks]
        assert "diameter_decreases_along_z" in types


# --- Slot tests ---

class TestSlot:
    def test_returns_part(self):
        from agentcad.features import slot
        s = slot(width=5, depth=3, height=20)
        assert s.volume > 0

    def test_registers_section_check(self):
        from agentcad.features import slot
        builder = ContractBuilder()
        slot(width=5, depth=3, height=20, builder=builder)
        assert len(builder.checks) == 1
        assert builder.checks[0]["type"] == "section_bbox_at_z"

    def test_direction_y(self):
        from agentcad.features import slot
        s = slot(width=5, depth=3, height=20, direction="y")
        assert s.volume > 0
