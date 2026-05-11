import math

import pytest

from agentcad.features import ContractBuilder, pie_slice


class TestPieSlice:
    def test_returns_part(self):
        ps = pie_slice(radius=10, angle=90, height=5)
        assert ps.volume > 0

    def test_volume_quarter(self):
        ps = pie_slice(radius=10, angle=90, height=5)
        expected = math.pi * 10**2 * 5 / 4
        assert abs(ps.volume - expected) < expected * 0.05

    def test_half_circle(self):
        ps = pie_slice(radius=10, angle=180, height=5)
        assert ps.volume > 0

    def test_full_circle(self):
        ps = pie_slice(radius=10, angle=360, height=5)
        assert ps.volume > 0

    def test_invalid_angle(self):
        with pytest.raises(ValueError, match="angle"):
            pie_slice(radius=10, angle=0, height=5)

    def test_invalid_radius(self):
        with pytest.raises(ValueError, match="radius"):
            pie_slice(radius=0, angle=90, height=5)

    def test_contract_registers_checks(self):
        b = ContractBuilder()
        pie_slice(radius=10, angle=90, height=5, builder=b)
        assert len(b.features) == 1
        assert len(b.checks) == 2