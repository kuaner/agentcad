import pytest

from agentcad.features import ContractBuilder, living_hinge_mask


class TestLivingHingeMask:
    def test_returns_part(self):
        lh = living_hinge_mask(length=30, thickness=3)
        assert lh.volume > 0

    def test_custom_foldangle(self):
        lh = living_hinge_mask(length=30, thickness=3, foldangle=45)
        assert lh.volume > 0

    def test_contract_registers_check(self):
        b = ContractBuilder()
        living_hinge_mask(length=30, thickness=3, builder=b)
        assert len(b.features) == 1
        assert len(b.checks) == 1
        assert b.checks[0]["type"] == "section_bbox_at_z"