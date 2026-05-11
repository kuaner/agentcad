import pytest

from agentcad.features import ContractBuilder, threaded_nut


class TestThreadedNut:
    @pytest.mark.slow
    def test_returns_part(self):
        n = threaded_nut("M3")
        assert n.volume > 0

    @pytest.mark.slow
    def test_m4_spec(self):
        n = threaded_nut("M4")
        assert n.volume > 0

    def test_invalid_spec(self):
        with pytest.raises((ValueError, KeyError)):
            threaded_nut("M42")

    @pytest.mark.slow
    def test_contract_registers_checks(self):
        b = ContractBuilder()
        threaded_nut("M3", builder=b, feature_id="m3_tnut")
        assert len(b.features) == 1
        assert len(b.checks) == 1