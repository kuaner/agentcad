from agentcad.features import ContractBuilder, stepped_bore


class TestSteppedBore:
    def test_plain_bore_returns_bore(self):
        bore = stepped_bore("M3", bore_kind="plain", through_depth=10)
        assert bore.through_r > 0

    def test_counterbore_returns_bore(self):
        bore = stepped_bore("M3_cap", bore_kind="counterbore", through_depth=10)
        assert bore.through_r > 0

    def test_plain_registers_one_check(self):
        b = ContractBuilder()
        stepped_bore("M3", bore_kind="plain", through_depth=10, builder=b)
        assert len(b.checks) == 2
        types = [c["type"] for c in b.checks]
        assert "inner_diameter_at_z" in types
        assert "hole_accessibility" in types

    def test_counterbore_registers_two_checks(self):
        b = ContractBuilder()
        stepped_bore("M3_cap", bore_kind="counterbore", through_depth=10, builder=b)
        assert len(b.checks) == 3
        types = [c["type"] for c in b.checks]
        assert "inner_diameter_at_z" in types
        assert "hole_accessibility" in types
