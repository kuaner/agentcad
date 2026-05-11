from agentcad.features import ContractBuilder, nut_trap


class TestNutTrap:
    def test_returns_part(self):
        nt = nut_trap("M3", depth=8)
        assert nt.volume > 0

    def test_top_orientation(self):
        nt = nut_trap("M3", depth=8, orientation="top")
        assert nt.volume > 0

    def test_contract_registers_checks(self):
        b = ContractBuilder()
        nut_trap("M3", depth=8, builder=b)
        assert len(b.features) == 1
        assert len(b.checks) == 1
        assert b.checks[0]["type"] == "section_bbox_at_z"