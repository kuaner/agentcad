import pytest

from agentcad.features import ContractBuilder, dovetail


class TestDovetail:
    def test_male_returns_part(self):
        dt = dovetail("male", width=10, height=6, slide=20)
        assert dt.volume > 0

    def test_female_returns_part(self):
        dt = dovetail("female", width=10, height=6, slide=20)
        assert dt.volume > 0

    def test_with_angle(self):
        dt = dovetail("male", width=10, height=6, slide=20, angle=30)
        assert dt.volume > 0

    def test_female_larger_than_male(self):
        male = dovetail("male", width=10, height=6, slide=20)
        female = dovetail("female", width=10, height=6, slide=20)
        assert female.volume > male.volume

    def test_invalid_gender(self):
        with pytest.raises(ValueError, match="gender"):
            dovetail("neutral", width=10, height=6, slide=20)

    def test_contract_registers_check(self):
        b = ContractBuilder()
        dovetail("male", width=10, height=6, slide=20, builder=b)
        assert len(b.features) == 1
        assert len(b.checks) == 1
        assert b.checks[0]["type"] == "bbox_size"