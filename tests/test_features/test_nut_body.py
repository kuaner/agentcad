import pytest

from agentcad.features import ContractBuilder, nut_body


class TestNutBody:
    def test_returns_part(self):
        nb = nut_body("M3")
        assert nb.volume > 0

    def test_hollow_bore(self):
        nb = nut_body("M3")
        # Has a bore hole — volume less than solid hex
        from build123d import BuildPart, BuildSketch, Polygon, extrude, Mode
        import math
        r = 3.2  # across-corners radius for M3
        hex_verts = [(r * math.cos(math.radians(60 * i + 30)),
                      r * math.sin(math.radians(60 * i + 30))) for i in range(6)]
        with BuildPart(mode=Mode.PRIVATE) as bp:
            with BuildSketch():
                Polygon(hex_verts)
            extrude(amount=2.4)
        solid_hex_vol = bp.part.volume
        assert nb.volume < solid_hex_vol

    def test_m4(self):
        nb = nut_body("M4")
        assert nb.volume > 0

    def test_contract_registers_checks(self):
        b = ContractBuilder()
        nut_body("M3", builder=b)
        assert len(b.features) == 1
        assert len(b.checks) == 2