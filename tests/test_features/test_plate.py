import pytest

from agentcad.features import ContractBuilder, plate


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
