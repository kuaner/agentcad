from agentcad.features import ContractBuilder, slot


class TestSlot:
    def test_returns_part(self):
        s = slot(width=5, depth=3, height=20)
        assert s.volume > 0

    def test_registers_section_check(self):
        builder = ContractBuilder()
        slot(width=5, depth=3, height=20, builder=builder)
        assert len(builder.checks) == 1
        assert builder.checks[0]["type"] == "section_bbox_at_z"

    def test_direction_y(self):
        s = slot(width=5, depth=3, height=20, direction="y")
        assert s.volume > 0
