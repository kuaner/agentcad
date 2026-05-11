import pytest

from agentcad.features import ContractBuilder, nema_mount


class TestNemaMount:
    def test_returns_part(self):
        nm = nema_mount(17)
        assert nm.volume > 0

    def test_all_sizes(self):
        for size in (8, 11, 14, 17, 23):
            nm = nema_mount(size)
            assert nm.volume > 0

    def test_custom_depth(self):
        nm = nema_mount(17, depth=10)
        assert nm.volume > 0

    def test_invalid_size(self):
        with pytest.raises(ValueError, match="size"):
            nema_mount(42)

    def test_contract_registers_checks(self):
        b = ContractBuilder()
        nema_mount(17, builder=b)
        assert len(b.features) == 1
        assert len(b.checks) == 2