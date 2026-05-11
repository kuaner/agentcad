import pytest

from agentcad.features import ContractBuilder, rib


class TestRib:
    def test_returns_part(self):
        r = rib(length=30, height=10, thickness=3)
        assert r.volume > 0

    def test_direction_y(self):
        r = rib(length=30, height=10, thickness=3, direction="y")
        assert r.volume > 0

    def test_registers_wall_thickness(self):
        builder = ContractBuilder()
        rib(length=30, height=10, thickness=3, builder=builder)
        assert len(builder.checks) == 1
        assert builder.checks[0]["type"] == "min_wall_thickness"

    def test_invalid_direction(self):
        with pytest.raises(ValueError, match="direction"):
            rib(length=30, height=10, thickness=3, direction="z")
