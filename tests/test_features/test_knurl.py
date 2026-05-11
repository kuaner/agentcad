import pytest

from agentcad.features.knurl import helical_knurl


class TestKnurl:
    def test_single_direction(self):
        grooves = helical_knurl(radius=20.0, height=20.0, diamond=False)
        assert len(grooves) > 0
        assert all(g.volume > 0 for g in grooves)

    def test_diamond(self):
        single = helical_knurl(radius=20.0, height=20.0, diamond=False)
        diamond = helical_knurl(radius=20.0, height=20.0, diamond=True)
        assert len(diamond) > len(single)
        assert all(g.volume > 0 for g in diamond)

    def test_invalid_params(self):
        with pytest.raises(ValueError):
            helical_knurl(radius=0, height=10.0)
        with pytest.raises(ValueError):
            helical_knurl(radius=20.0, height=-5.0)
