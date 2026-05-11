import pytest

from agentcad.features import ContractBuilder, snap_pin, snap_pin_socket


class TestSnapPin:
    def test_returns_part(self):
        pin = snap_pin("small")
        assert pin.volume > 0

    def test_all_sizes(self):
        for size in ("tiny", "small", "medium", "standard"):
            pin = snap_pin(size)
            assert pin.volume > 0

    def test_rounded_tip(self):
        pin = snap_pin("small", pointed=False)
        assert pin.volume > 0

    def test_custom_diameter(self):
        pin = snap_pin("small", diameter=5.0)
        assert pin.volume > 0

    def test_socket_returns_part(self):
        sock = snap_pin_socket("small")
        assert sock.volume > 0

    def test_socket_round(self):
        sock = snap_pin_socket("small", fixed=False)
        assert sock.volume > 0

    def test_socket_larger_than_pin(self):
        pin = snap_pin("standard")
        sock = snap_pin_socket("standard", fixed=False)
        assert sock.volume > pin.volume

    def test_invalid_size(self):
        with pytest.raises(ValueError, match="size"):
            snap_pin("huge")

    def test_contract_registers_checks(self):
        b = ContractBuilder()
        snap_pin("small", builder=b)
        assert len(b.features) == 1
        assert len(b.checks) == 2

    def test_socket_contract(self):
        b = ContractBuilder()
        snap_pin_socket("small", builder=b)
        assert len(b.features) == 1
        assert len(b.checks) == 2