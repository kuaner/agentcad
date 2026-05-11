from agentcad.features import ContractBuilder, teardrop


class TestTeardrop:
    def test_returns_part(self):
        td = teardrop(diameter=6, height=10)
        assert td.volume > 0

    def test_custom_angle(self):
        td = teardrop(diameter=6, height=10, angle=30)
        assert td.volume > 0

    def test_contract_registers_check(self):
        b = ContractBuilder()
        teardrop(diameter=6, height=10, builder=b)
        assert len(b.features) == 1
        assert len(b.checks) == 1
        assert b.checks[0]["type"] == "inner_diameter_at_z"