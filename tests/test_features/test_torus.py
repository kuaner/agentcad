import math

import pytest

from agentcad.features import ContractBuilder, torus


class TestTorus:
    def test_returns_part(self):
        t = torus(10, 3)
        assert t.volume > 0

    def test_volume_approximate(self):
        t = torus(10, 3)
        expected = 2 * math.pi**2 * 10 * 3**2
        assert abs(t.volume - expected) < expected * 0.1

    def test_invalid_major(self):
        with pytest.raises(ValueError, match="major_radius"):
            torus(0, 3)

    def test_invalid_minor(self):
        with pytest.raises(ValueError, match="minor_radius"):
            torus(10, 0)

    def test_contract_registers_checks(self):
        b = ContractBuilder()
        torus(10, 3, builder=b)
        assert len(b.features) == 1
        assert len(b.checks) == 2