import pytest

from agentcad.features import ContractBuilder, prismoid


class TestPrismoid:
    def test_returns_part(self):
        p = prismoid((30, 20), (20, 10), 15)
        assert p.volume > 0

    def test_uniform_sizes(self):
        p = prismoid((20, 20), (20, 20), 10)
        assert p.volume > 0

    def test_contract_registers_bbox(self):
        b = ContractBuilder()
        prismoid((30, 20), (20, 10), 15, builder=b)
        assert len(b.features) == 1
        assert b.features[0]["id"] == "prismoid"
        assert len(b.checks) == 1
        assert b.checks[0]["type"] == "bbox_size"

    def test_custom_feature_id(self):
        b = ContractBuilder()
        prismoid((30, 20), (20, 10), 15, builder=b, feature_id="tapered_base")
        assert b.features[0]["id"] == "tapered_base"