import pytest

from agentcad.features import ContractBuilder, rect_tube


class TestRectTube:
    def test_returns_part(self):
        rt = rect_tube((40, 30, 20), wall=2)
        assert rt.volume > 0

    def test_hollow(self):
        rt = rect_tube((40, 30, 20), wall=2)
        solid_volume = 40 * 30 * 20
        assert rt.volume < solid_volume

    def test_invalid_size(self):
        with pytest.raises(ValueError, match="size"):
            rect_tube((40, 30), wall=2)

    def test_contract_registers_checks(self):
        b = ContractBuilder()
        rect_tube((40, 30, 20), wall=2, builder=b)
        assert len(b.features) == 1
        assert len(b.checks) == 2