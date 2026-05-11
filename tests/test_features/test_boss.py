from agentcad.features import ContractBuilder, boss


class TestBoss:
    def test_returns_part(self):
        b = boss(diameter=10, height=5)
        assert b.volume > 0

    def test_with_hole_check(self):
        builder = ContractBuilder()
        boss(diameter=10, height=5, inner_diameter=4, builder=builder)
        assert len(builder.checks) == 1
        assert builder.checks[0]["type"] == "inner_diameter_at_z"

    def test_without_hole_no_check(self):
        builder = ContractBuilder()
        boss(diameter=10, height=5, builder=builder)
        assert len(builder.checks) == 0
        assert len(builder.features) == 1
