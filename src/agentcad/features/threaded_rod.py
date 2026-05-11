"""Threaded rod helper: ISO-standard thread profile."""
from __future__ import annotations

from typing import TYPE_CHECKING

from build123d import (
    BuildPart,
    Location,
    Mode,
    Part,
)

from ..hardware.screws import Screw, screw, COARSE_PITCH
from .thread import sinusoidal_thread

if TYPE_CHECKING:
    from .contract import ContractBuilder


def threaded_rod(
    spec: str | Screw,
    length: float,
    *,
    n_starts: int = 1,
    builder: ContractBuilder | None = None,
    feature_id: str = "threaded_rod",
) -> Part:
    """Create a threaded rod with ISO-standard thread profile.

    Uses the coarse pitch from the ISO metric thread table and the
    ``sinusoidal_thread`` helper to generate the helical profile.

    Parameters
    ----------
    spec : str or Screw
        Screw spec like "M3" or "M4" — determines diameter and pitch.
    length : float
        Rod length along Z (mm).
    n_starts : int
        Number of thread starts (1 = single-start, 2+ = multi-start).
    builder : ContractBuilder | None
        If provided, registers feature and checks.
    feature_id : str
        Base ID for entries.

    Returns
    -------
    Part
        The threaded rod.
    """
    s = screw(spec) if isinstance(spec, str) else spec
    pitch = COARSE_PITCH.get(s.nominal_diameter, 0.0)
    if pitch == 0.0:
        raise ValueError(f"no coarse pitch for diameter {s.nominal_diameter}; specify a standard M-size")

    rod = sinusoidal_thread(
        radius=s.nominal_diameter / 2,
        pitch=pitch,
        height=length,
        n_starts=n_starts,
    )

    if builder is not None:
        builder.add(
            feature={
                "id": feature_id,
                "description": f"threaded_rod {s.name} pitch={pitch}mm length={length}mm",
            },
            checks=[
                {
                    "id": f"{feature_id}_od",
                    "type": "outer_diameter_at_z",
                    "z": length / 2,
                    "center": [0, 0],
                    "expected": s.nominal_diameter,
                    "tolerance": 1.0,
                    "feature_ref": feature_id,
                },
            ],
        )

    return rod