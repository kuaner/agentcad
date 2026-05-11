import pytest

from build123d import (
    Align,
    BuildPart,
    Cylinder,
    Location,
    Mode,
    add,
)

from agentcad.features.thread import sinusoidal_thread


class TestThread:
    def test_single_start(self):
        thread = sinusoidal_thread(radius=20.0, pitch=9.0, height=10.0, n_starts=1)
        assert thread.volume > 0
        assert len(thread.solids()) == 1

    def test_three_start(self):
        thread = sinusoidal_thread(radius=20.0, pitch=9.0, height=10.0, n_starts=3)
        assert thread.volume > 0
        single = sinusoidal_thread(radius=20.0, pitch=9.0, height=10.0, n_starts=1)
        assert thread.volume > single.volume * 2

    def test_external_body_union(self):
        with BuildPart() as body:
            Cylinder(radius=22.0, height=15.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
            thread = sinusoidal_thread(radius=20.0, pitch=9.0, height=10.0, n_starts=3)
            add(thread.moved(Location((0, 0, 5))))
        part = body.part
        assert part.volume > 0
        assert len(part.solids()) == 1

    def test_internal_lid_subtract(self):
        with BuildPart() as lid:
            Cylinder(radius=25.0, height=12.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
            Cylinder(radius=20.2, height=10.0, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
            thread = sinusoidal_thread(radius=20.0, pitch=9.0, height=10.0, n_starts=3)
            add(thread, mode=Mode.SUBTRACT)
        part = lid.part
        assert part.volume > 0

    def test_invalid_params(self):
        with pytest.raises(ValueError):
            sinusoidal_thread(radius=0, pitch=9.0, height=10.0)
        with pytest.raises(ValueError):
            sinusoidal_thread(radius=20.0, pitch=0, height=10.0)
        with pytest.raises(ValueError):
            sinusoidal_thread(radius=20.0, pitch=9.0, height=-5.0)
        with pytest.raises(ValueError):
            sinusoidal_thread(radius=20.0, pitch=9.0, height=10.0, n_starts=0)
        with pytest.raises(ValueError):
            sinusoidal_thread(radius=20.0, pitch=9.0, height=10.0, n_starts=1.5)
