import pytest

from agentcad.features import ContractBuilder, hex_panel


class TestHexPanel:
    def test_returns_part(self):
        hp = hex_panel((50, 50), strut=1, spacing=8)
        assert hp.volume > 0

    def test_with_explicit_height(self):
        hp = hex_panel((50, 50, 5), strut=1, spacing=8)
        assert hp.volume > 0

    def test_volume_less_than_solid(self):
        hp = hex_panel((50, 50, 3), strut=1, spacing=8)
        solid = 50 * 50 * 3
        assert hp.volume < solid

    def test_contract_registers_checks(self):
        b = ContractBuilder()
        hex_panel((50, 50), strut=1, spacing=8, builder=b)
        assert len(b.features) == 1
        assert len(b.checks) == 2

    def test_invalid_size(self):
        with pytest.raises(ValueError, match="size"):
            hex_panel((50,), strut=1, spacing=8)