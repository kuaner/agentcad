import pytest

from agentcad.features import ContractBuilder, spur_gear


class TestSpurGear:
    def test_returns_part(self):
        gear = spur_gear(teeth=12, module=2, thickness=5)
        assert gear.volume > 0

    def test_with_shaft_hole(self):
        gear = spur_gear(teeth=20, module=1.5, thickness=8, shaft_diameter=5)
        assert gear.volume > 0

    def test_shaft_reduces_volume(self):
        solid = spur_gear(teeth=16, module=2, thickness=6)
        hollow = spur_gear(teeth=16, module=2, thickness=6, shaft_diameter=4)
        assert hollow.volume < solid.volume

    def test_different_pressure_angle(self):
        gear = spur_gear(teeth=12, module=2, thickness=5, pressure_angle=14.5)
        assert gear.volume > 0

    def test_with_backlash(self):
        gear = spur_gear(teeth=12, module=2, thickness=5, backlash=0.1)
        assert gear.volume > 0

    def test_contract_registers_checks(self):
        b = ContractBuilder()
        spur_gear(teeth=12, module=2, thickness=5, builder=b)
        assert len(b.features) == 1
        assert len(b.checks) == 2

    def test_shaft_check(self):
        b = ContractBuilder()
        spur_gear(teeth=12, module=2, thickness=5, shaft_diameter=3, builder=b)
        assert len(b.checks) == 3

    def test_invalid_teeth(self):
        with pytest.raises(ValueError, match="teeth"):
            spur_gear(teeth=4, module=2, thickness=5)

    def test_invalid_module(self):
        with pytest.raises(ValueError, match="module"):
            spur_gear(teeth=12, module=0, thickness=5)