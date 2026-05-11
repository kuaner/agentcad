import pytest

from agentcad.features import ContractBuilder, chamfer_mask


class TestChamferMask:
    def test_returns_part(self):
        c = chamfer_mask(20, edge="z", size=2)
        assert c.volume > 0

    def test_edge_x(self):
        c = chamfer_mask(20, edge="x", size=2)
        assert c.volume > 0

    def test_invalid_edge(self):
        with pytest.raises(ValueError, match="edge"):
            chamfer_mask(20, edge="w", size=2)

    def test_contract_registers_feature(self):
        b = ContractBuilder()
        chamfer_mask(20, edge="z", size=2, builder=b)
        assert len(b.features) == 1
        assert b.features[0]["id"] == "chamfer"