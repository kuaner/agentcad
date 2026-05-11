import pytest

from agentcad.features import ContractBuilder, ring_gear


class TestRingGear:
    def test_returns_part(self):
        g = ring_gear(20, 2, 5)
        assert g.volume > 0

    def test_small_gear(self):
        g = ring_gear(12, 1.5, 4, rim_width=5)
        assert g.volume > 0

    def test_custom_rim(self):
        g = ring_gear(20, 2, 5, rim_width=8)
        assert g.volume > 0

    def test_invalid_teeth(self):
        with pytest.raises(ValueError, match="teeth"):
            ring_gear(3, 2, 5)

    def test_contract_registers_checks(self):
        b = ContractBuilder()
        ring_gear(20, 2, 5, builder=b, feature_id="ring")
        assert len(b.features) == 1
        assert len(b.checks) == 2