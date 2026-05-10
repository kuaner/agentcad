from __future__ import annotations

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
from agentcad.features.knurl import helical_knurl


def test_thread_single_start():
    thread = sinusoidal_thread(radius=20.0, pitch=9.0, height=10.0, n_starts=1)
    assert thread.volume > 0
    assert len(thread.solids()) == 1


def test_thread_three_start():
    thread = sinusoidal_thread(radius=20.0, pitch=9.0, height=10.0, n_starts=3)
    assert thread.volume > 0
    single = sinusoidal_thread(radius=20.0, pitch=9.0, height=10.0, n_starts=1)
    assert thread.volume > single.volume * 2


def test_thread_external_body_union():
    with BuildPart() as body:
        Cylinder(radius=22.0, height=15.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
        thread = sinusoidal_thread(radius=20.0, pitch=9.0, height=10.0, n_starts=3)
        add(thread.moved(Location((0, 0, 5))))
    part = body.part
    assert part.volume > 0
    assert len(part.solids()) == 1


def test_thread_internal_lid_subtract():
    with BuildPart() as lid:
        Cylinder(radius=25.0, height=12.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
        Cylinder(radius=20.2, height=10.0, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
        thread = sinusoidal_thread(radius=20.0, pitch=9.0, height=10.0, n_starts=3)
        add(thread, mode=Mode.SUBTRACT)
    part = lid.part
    assert part.volume > 0


def test_thread_invalid_params():
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


def test_knurl_single_direction():
    grooves = helical_knurl(radius=20.0, height=20.0, diamond=False)
    assert len(grooves) > 0
    assert all(g.volume > 0 for g in grooves)


def test_knurl_diamond():
    single = helical_knurl(radius=20.0, height=20.0, diamond=False)
    diamond = helical_knurl(radius=20.0, height=20.0, diamond=True)
    assert len(diamond) > len(single)
    assert all(g.volume > 0 for g in diamond)


def test_knurl_invalid_params():
    with pytest.raises(ValueError):
        helical_knurl(radius=0, height=10.0)
    with pytest.raises(ValueError):
        helical_knurl(radius=20.0, height=-5.0)
