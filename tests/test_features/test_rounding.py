import pytest

from agentcad.features import ContractBuilder, rounding_mask


class TestRoundingMask:
    def test_returns_part(self):
        rm = rounding_mask(10, size=2)
        assert rm.volume > 0

    def test_edge_x(self):
        rm = rounding_mask(10, edge="x", size=2)
        assert rm.volume > 0

    def test_edge_y(self):
        rm = rounding_mask(10, edge="y", size=2)
        assert rm.volume > 0

    def test_larger_than_chamfer(self):
        from agentcad.features import chamfer_mask
        rm = rounding_mask(10, size=2)
        cm = chamfer_mask(10, size=2)
        # Rounding mask (quarter circle) has more volume than chamfer (triangle)
        assert rm.volume > cm.volume

    def test_invalid_edge(self):
        with pytest.raises(ValueError, match="edge"):
            rounding_mask(10, edge="w")

    def test_contract_registers_feature(self):
        b = ContractBuilder()
        rounding_mask(10, size=2, builder=b)
        assert len(b.features) == 1
        assert len(b.checks) == 0  # cosmetic, no auto-checks