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
        assert len(builder.checks) == 2
        assert {check["type"] for check in builder.checks} == {"min_wall_thickness", "feature_position"}
        assert builder.failure_modes[0]["mode"] == "suspended_rib"

    def test_invalid_direction(self):
        with pytest.raises(ValueError, match="direction"):
            rib(length=30, height=10, thickness=3, direction="z")
