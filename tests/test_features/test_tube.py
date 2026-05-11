from agentcad.features import ContractBuilder, tube


class TestTube:
    def test_returns_part(self):
        t = tube(outer_diameter=20, inner_diameter=15, height=10)
        assert t.volume > 0

    def test_contract_registers_checks(self):
        b = ContractBuilder()
        tube(outer_diameter=20, inner_diameter=15, height=10, builder=b)
        assert len(b.checks) == 2
        types = [c["type"] for c in b.checks]
        assert "outer_diameter_at_z" in types
        assert "inner_diameter_at_z" in types

    def test_custom_feature_id(self):
        b = ContractBuilder()
        tube(outer_diameter=20, inner_diameter=15, height=10, builder=b, feature_id="spacer")
        assert b.features[0]["id"] == "spacer"
        assert b.checks[0]["id"] == "spacer_outer"