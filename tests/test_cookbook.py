"""P3.4 Executable helper cookbook: testable snippets for common patterns.

Each snippet imports and builds geometry. Snippets that use ContractBuilder
also produce valid design checks. These snippets serve as the authoritative
reference for helper usage patterns.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from agentcad.features import (
    ContractBuilder,
    screw_hole,
    boss,
    snap_pin,
    snap_pin_socket,
    dovetail,
    spur_gear,
    ring_gear,
    tube,
    plate,
)


# ── Pattern 1: Screw holes and counterbores ────────────────────────────────


class TestScrewHoleCookbook:
    """Screw hole pattern: clearance hole + counterbore with ContractBuilder."""

    def test_clearance_screw_hole_builds(self):
        from build123d import BuildPart, Box
        with BuildPart() as bp:
            Box(20, 20, 10)
            sh = screw_hole("M3", kind="clearance", head="counterbore")
            sh.cut()
        assert bp.part.volume > 0

    def test_clearance_screw_hole_with_builder_emits_checks(self):
        b = ContractBuilder()
        screw_hole("M3", kind="clearance", head="counterbore", builder=b, feature_id="m3_hole")
        assert len(b.checks) > 0
        types = [c["type"] for c in b.checks]
        assert "inner_diameter_at_z" in types

    def test_screw_hole_builder_emits_interface(self):
        b = ContractBuilder()
        screw_hole("M3", kind="clearance", builder=b, feature_id="m3_hole")
        assert "m3_hole_screw_axis" in b.interfaces
        iface = b.interfaces["m3_hole_screw_axis"]
        assert iface["kind"] == "screw_axis"


# ── Pattern 2: Standoffs and bosses ───────────────────────────────────────


class TestBossCookbook:
    """Boss pattern: raised standoff with inner bore and ContractBuilder."""

    def test_boss_with_inner_bore_builds(self):
        b = boss(diameter=8, height=12, inner_diameter=4)
        assert b.volume > 0

    def test_boss_with_builder_emits_checks(self):
        builder = ContractBuilder()
        boss(diameter=8, height=12, inner_diameter=4, builder=builder, feature_id="standoff")
        assert len(builder.checks) > 0
        types = [c["type"] for c in builder.checks]
        assert "inner_diameter_at_z" in types

    def test_boss_metadata_has_feature_and_check(self):
        builder = ContractBuilder()
        boss(diameter=8, height=12, inner_diameter=4, builder=builder, feature_id="standoff")
        meta = builder.to_metadata()
        assert meta["schema"] == "agentcad.part.metadata.v1"
        assert len(builder.features) > 0


# ── Pattern 3: Snap pin/socket ────────────────────────────────────────────


class TestSnapPinCookbook:
    """Snap-fit pattern: pin + socket pair with interface metadata."""

    def test_snap_pin_builds(self):
        pin = snap_pin(size="small")
        assert pin.volume > 0

    def test_snap_socket_builds(self):
        socket = snap_pin_socket(size="small")
        assert socket.volume > 0

    def test_pin_with_builder_emits_interface(self):
        builder = ContractBuilder()
        snap_pin(size="small", builder=builder, feature_id="clip")
        assert "clip_pin" in builder.interfaces
        assert builder.interfaces["clip_pin"]["kind"] == "snap_pin"

    def test_socket_with_builder_emits_interface(self):
        builder = ContractBuilder()
        snap_pin_socket(size="small", builder=builder, feature_id="clip")
        assert "clip_socket" in builder.interfaces
        assert builder.interfaces["clip_socket"]["kind"] == "snap_socket"


# ── Pattern 4: Dovetail ───────────────────────────────────────────────────


class TestDovetailCookbook:
    """Dovetail pattern: male/female rail pair."""

    def test_male_dovetail_builds(self):
        male = dovetail(gender="male", width=6, height=4, slide=20)
        assert male.volume > 0

    def test_female_dovetail_builds(self):
        female = dovetail(gender="female", width=6, height=4, slide=20)
        assert female.volume > 0

    def test_dovetail_with_builder_emits_feature(self):
        builder = ContractBuilder()
        dovetail(gender="male", width=6, height=4, slide=20, builder=builder, feature_id="rail")
        assert len(builder.features) > 0
        assert len(builder.checks) > 0


# ── Pattern 5: Gear pair ──────────────────────────────────────────────────


class TestGearPairCookbook:
    """Gear pair pattern: spur gear + ring gear."""

    def test_spur_gear_builds(self):
        gear = spur_gear(teeth=12, module=2.0, thickness=5)
        assert gear.volume > 0

    def test_ring_gear_builds(self):
        rg = ring_gear(teeth=24, module=2.0, thickness=5, rim_width=4)
        assert rg.volume > 0

    def test_spur_gear_with_builder_emits_checks(self):
        builder = ContractBuilder()
        spur_gear(teeth=12, module=2.0, thickness=5, builder=builder, feature_id="drive_gear")
        assert len(builder.checks) > 0
        types = [c["type"] for c in builder.checks]
        assert "bbox_size" in types
        assert "outer_diameter_at_z" in types


# ── Pattern 6: Assembly interface metadata ────────────────────────────────


class TestAssemblyInterfaceCookbook:
    """Assembly interface pattern: tube outer sleeve + inner bore for mating."""

    def test_tube_with_builder_emits_both_interfaces(self):
        builder = ContractBuilder()
        tube(outer_diameter=20, inner_diameter=15, height=10, builder=builder)
        assert "tube_outer_sleeve" in builder.interfaces
        assert "tube_inner_bore" in builder.interfaces
        assert builder.interfaces["tube_outer_sleeve"]["kind"] == "cylindrical_male"
        assert builder.interfaces["tube_inner_bore"]["kind"] == "cylindrical_female"

    def test_plate_with_builder_emits_features(self):
        builder = ContractBuilder()
        plate(width=40, depth=30, thickness=5, builder=builder, feature_id="base_plate")
        assert len(builder.features) > 0
        assert len(builder.checks) > 0

    def test_contract_builder_write_metadata_merges(self):
        builder = ContractBuilder(units="mm")
        tube(outer_diameter=20, inner_diameter=15, height=10, builder=builder, feature_id="spacer")
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            model_dir = project / "models" / "spacer"
            model_dir.mkdir(parents=True)
            builder.write_metadata_to(project, "spacer")
            meta_path = model_dir / "metadata.json"
            assert meta_path.exists()
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            assert "spacer_outer_sleeve" in meta["interfaces"]