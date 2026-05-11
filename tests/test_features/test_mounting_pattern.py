from agentcad.features import ContractBuilder, mounting_pattern


class TestMountingPattern:
    def test_square_pattern_returns_holes(self):
        holes = mounting_pattern("M3", kind="square", spacing=25)
        assert len(holes.positions) == 4

    def test_rectangular_pattern(self):
        holes = mounting_pattern("M3", kind="rectangular", spacing_x=30, spacing_y=20)
        assert len(holes.positions) == 4

    def test_linear_pattern(self):
        holes = mounting_pattern("M3", kind="linear", spacing=25, count=4)
        assert len(holes.positions) == 4

    def test_registers_checks(self):
        b = ContractBuilder()
        mounting_pattern("M3", kind="square", spacing=25, builder=b)
        assert len(b.features) == 1
        assert b.features[0]["id"] == "mounting_holes"
        # square = 4 holes x (diameter + accessibility) = 8 checks
        assert len(b.checks) == 8

    def test_custom_screw_spec(self):
        b = ContractBuilder()
        mounting_pattern("M4_cap", kind="square", spacing=30, builder=b)
        assert "M4_cap" in b.features[0]["description"]

    def test_linear_pattern_check_count(self):
        b = ContractBuilder()
        mounting_pattern("M3", kind="linear", spacing=20, count=3, builder=b)
        # 3 holes x (diameter + accessibility) = 6 checks
        assert len(b.checks) == 6
