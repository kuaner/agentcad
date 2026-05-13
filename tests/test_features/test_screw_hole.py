from agentcad.features import ContractBuilder, screw_hole, ScrewHole


class TestScrewHole:
    def test_clearance_kind(self):
        b = ContractBuilder()
        sh = screw_hole("M3", through_depth=10, kind="clearance", builder=b)
        assert sh.through_r > 0
        assert len(b.checks) >= 1

    def test_tap_kind(self):
        b = ContractBuilder()
        sh = screw_hole("M3", through_depth=10, kind="tap", builder=b)
        assert sh.through_r > 0
        through = next(check for check in b.checks if check["id"] == "screw_hole_through")
        assert through["expected"] == sh.through_r * 2

    def test_plain_head(self):
        b = ContractBuilder()
        sh = screw_hole("M3", through_depth=10, kind="clearance", head="plain", builder=b)
        assert sh.recess_depth == 0

    def test_is_screw_hole_instance(self):
        sh = screw_hole("M3", through_depth=10)
        assert isinstance(sh, ScrewHole)
