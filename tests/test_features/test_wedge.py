import pytest

from agentcad.features import ContractBuilder, wedge


class TestWedge:
    def test_returns_part(self):
        w = wedge(30, 10, 15)
        assert w.volume > 0

    def test_direction_y(self):
        w = wedge(30, 10, 15, direction="+y")
        assert w.volume > 0
        bb = w.bounding_box()
        assert bb.max.Y - bb.min.Y == pytest.approx(30, abs=1.0)

    def test_invalid_direction(self):
        with pytest.raises(ValueError, match="direction"):
            wedge(30, 10, 15, direction="z")

    def test_contract_registers_bbox(self):
        b = ContractBuilder()
        wedge(30, 10, 15, builder=b)
        assert len(b.features) == 1
        assert len(b.checks) == 1
        assert b.checks[0]["type"] == "bbox_size"