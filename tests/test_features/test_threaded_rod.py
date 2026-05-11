import pytest

from agentcad.features import ContractBuilder, threaded_rod


class TestThreadedRod:
    def test_returns_part(self):
        rod = threaded_rod("M3", length=20)
        assert rod.volume > 0

    def test_multi_start(self):
        rod = threaded_rod("M4", length=20, n_starts=2)
        assert rod.volume > 0

    def test_contract_registers_check(self):
        b = ContractBuilder()
        threaded_rod("M3", length=20, builder=b)
        assert len(b.features) == 1
        assert len(b.checks) == 1
        assert b.checks[0]["type"] == "outer_diameter_at_z"

    def test_non_standard_diameter_raises(self):
        with pytest.raises(ValueError, match="coarse pitch"):
            # Use a Screw with diameter that has no coarse pitch entry
            from agentcad.hardware.screws import Screw
            fake = Screw(
                name="M99_custom", nominal_diameter=99.0, head_style="cap",
                head_diameter=0, head_height=0, socket_depth=0, socket_af=0,
                max_thread_length=0, tap_radius=0, clearance_radius=0,
            )
            threaded_rod(fake, length=10)