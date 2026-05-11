from agentcad.features import ContractBuilder, duct_socket


class TestDuctSocket:
    def test_returns_part(self):
        ds = duct_socket(outer_diameter=80, inner_diameter=79.4, length=28)
        assert ds.volume > 0

    def test_registers_id_check(self):
        builder = ContractBuilder()
        duct_socket(outer_diameter=80, inner_diameter=79.4, length=28, builder=builder)
        assert len(builder.checks) == 1
        assert builder.checks[0]["type"] == "inner_diameter_at_z"
