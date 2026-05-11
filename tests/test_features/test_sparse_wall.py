import pytest

from agentcad.features import ContractBuilder, sparse_wall


class TestSparseWall:
    def test_returns_part(self):
        w = sparse_wall((50, 30), strut=2, spacing=10)
        assert w.volume > 0

    def test_3d_size(self):
        w = sparse_wall((50, 30, 10), strut=2, spacing=10)
        assert w.volume > 0

    def test_contract_registers_checks(self):
        b = ContractBuilder()
        sparse_wall((50, 30), strut=2, spacing=10, builder=b, feature_id="wall")
        assert len(b.features) == 1
        assert len(b.checks) == 2

    def test_invalid_size_tuple(self):
        with pytest.raises(ValueError, match="size"):
            sparse_wall((50,), strut=2, spacing=10)

    def test_small_spacing(self):
        w = sparse_wall((20, 20), strut=2, spacing=5)
        assert w.volume > 0