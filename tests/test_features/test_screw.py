import pytest

from agentcad.features import ContractBuilder, screw


class TestScrew:
    @pytest.mark.slow
    def test_returns_part(self):
        s = screw("M3", length=12)
        assert s.volume > 0

    @pytest.mark.slow
    def test_m5_spec(self):
        s = screw("M5", length=20)
        assert s.volume > 0

    @pytest.mark.slow
    def test_custom_position(self):
        s = screw("M3", length=12, center=(10, 20), base_z=5)
        assert s.volume > 0

    @pytest.mark.slow
    def test_screw_object_spec(self):
        from agentcad.hardware.screws import screw as screw_lookup
        s_obj = screw_lookup("M4")
        s = screw(s_obj, length=16)
        assert s.volume > 0