"""Tests for hardware dimension tables."""
from __future__ import annotations

import pytest

from agentcad.hardware import Screw, Nut, Washer, Insert, SCREWS, NUTS, WASHERS, INSERTS, screw, nut, washer, insert


class TestScrews:
    def test_m3_cap_lookup(self):
        s = screw("M3_cap")
        assert s.nominal_diameter == 3.0
        assert s.head_style == "cap"
        assert s.head_diameter == 5.5
        assert s.head_height == 3.0
        assert s.tap_radius == 1.25
        assert s.clearance_radius == 1.65

    def test_shorthand_defaults_to_cap(self):
        assert screw("M3").name == "M3_cap"
        assert screw("M4").name == "M4_cap"

    def test_coarse_pitch(self):
        assert screw("M3").pitch == 0.5
        assert screw("M6").pitch == 1.0
        assert screw("M8").pitch == 1.25

    def test_counterbore_diameter(self):
        s = screw("M3_cap")
        assert s.counterbore_diameter() == pytest.approx(5.9)

    def test_through_hole_diameter(self):
        s = screw("M3_cap")
        assert s.through_hole_diameter("tight") == pytest.approx(3.0)
        assert s.through_hole_diameter("normal") == pytest.approx(3.3)
        assert s.through_hole_diameter("loose") == pytest.approx(3.6)

    def test_all_head_styles_represented(self):
        styles = {s.head_style for s in SCREWS.values()}
        assert "cap" in styles
        assert "pan" in styles
        assert "hex" in styles
        assert "cs_cap" in styles
        assert "dome" in styles
        assert "grub" in styles

    def test_unknown_screw_raises(self):
        with pytest.raises(KeyError):
            screw("M99_cap")

    def test_full_size_range(self):
        for dia in [2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0]:
            assert f"M{dia:g}_cap" in SCREWS or f"M{int(dia)}_cap" in SCREWS


class TestNuts:
    def test_m3_nut_lookup(self):
        n = nut("M3_nut")
        assert n.screw_diameter == 3.0
        assert n.thickness == 2.4
        assert n.trap_depth == 3.0
        assert n.style == "hex"

    def test_shorthand_defaults_to_hex(self):
        assert nut("M3").name == "M3_nut"
        assert nut("M4").name == "M4_nut"

    def test_across_flats(self):
        import math
        n = nut("M3_nut")
        expected = 6.4 * math.cos(math.pi / 6)
        assert n.width_across_flats == pytest.approx(expected, abs=0.01)

    def test_thin_square_nuts(self):
        n = nut("M3_thin_square")
        assert n.style == "thin_square"
        assert n.screw_diameter == 3.0

    def test_t_nuts(self):
        n = nut("M3_t_nut")
        assert n.style == "t_nut"

    def test_unknown_nut_raises(self):
        with pytest.raises(KeyError):
            nut("M99_nut")


class TestWashers:
    def test_m3_standard(self):
        w = washer("M3")
        assert w.outer_diameter == 7.0
        assert w.thickness == 0.5
        assert w.kind == "standard"

    def test_penny_washer(self):
        w = washer("M3_penny")
        assert w.outer_diameter == 12.0
        assert w.kind == "penny"

    def test_spring_washer(self):
        w = washer("M4_spring")
        assert w.kind == "spring"

    def test_unknown_washer_raises(self):
        with pytest.raises(KeyError):
            washer("M99")


class TestInserts:
    def test_f1bm3(self):
        ins = insert("F1BM3")
        assert ins.screw_diameter == 3.0
        assert ins.outer_diameter == 4.6
        assert ins.hole_diameter == 4.0
        assert ins.kind == "heat_set"

    def test_cnck_series(self):
        ins = insert("CNCKM5")
        assert ins.screw_diameter == 5.0
        assert ins.kind == "heat_set"

    def test_threaded_insert(self):
        ins = insert("M5x12")
        assert ins.kind == "threaded"
        assert ins.length == 12.0

    def test_wall_thickness(self):
        ins = insert("F1BM3")
        assert ins.wall_thickness == pytest.approx(0.8)

    def test_unknown_insert_raises(self):
        with pytest.raises(KeyError):
            insert("XYZ999")
