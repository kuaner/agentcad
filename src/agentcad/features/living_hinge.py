"""Living hinge mask: FDM-printable flex hinge (subtract from part)."""
from __future__ import annotations

import math

from typing import TYPE_CHECKING

from build123d import (
    BuildPart,
    BuildSketch,
    Location,
    Mode,
    Part,
    Plane,
    Rectangle,
    loft,
)

if TYPE_CHECKING:
    from .contract import ContractBuilder


def living_hinge_mask(
    length: float,
    thickness: float,
    *,
    layerheight: float = 0.2,
    foldangle: float = 90.0,
    center: tuple[float, float] = (0.0, 0.0),
    base_z: float = 0.0,
    builder: ContractBuilder | None = None,
    feature_id: str = "living_hinge",
) -> Part:
    """Create a living hinge mask for FDM-printable flex joints.

    Returns a trapezoidal negative solid.  Subtract it from your part
    to create a thin flexible bridge that can bend without breaking.
    The remaining material at the hinge line is ``2 * layerheight``
    thick, which is thin enough to flex but thick enough to print.

    Parameters
    ----------
    length : float
        Hinge length along X (mm).
    thickness : float
        Material thickness the hinge cuts through (mm).
    layerheight : float
        Expected FDM layer height; determines remaining hinge
        thickness (2 * layerheight). Default: 0.2.
    foldangle : float
        Interior fold angle in degrees. Controls the taper width
        above the hinge gap. Default: 90.
    center : tuple[float, float]
        XY center position.
    base_z : float
        Z position of the mask base.
    builder : ContractBuilder | None
        If provided, registers feature and checks.
    feature_id : str
        Base ID for entries.

    Returns
    -------
    Part
        The hinge mask solid (subtract from your part).
    """
    cx, cy = center

    gap_bottom = layerheight * 2
    gap_top = layerheight * 2 + 2 * thickness * math.tan(math.radians(foldangle / 2))

    # Offset mask upward by gap_bottom so the hinge material is thin
    mask_base_z = base_z + gap_bottom

    with BuildPart(mode=Mode.PRIVATE) as bp:
        with BuildSketch(Plane(origin=(cx, cy, mask_base_z))):
            Rectangle(length, gap_bottom)
        with BuildSketch(Plane(origin=(cx, cy, mask_base_z + thickness - gap_bottom))):
            Rectangle(length, gap_top)
        loft()

    result = bp.part

    if builder is not None:
        mid_z = base_z + thickness / 2
        builder.add(
            feature={
                "id": feature_id,
                "description": f"living_hinge l={length}mm t={thickness}mm angle={foldangle}deg",
            },
            checks=[
                {
                    "id": f"{feature_id}_section",
                    "type": "section_bbox_at_z",
                    "z": mid_z,
                    "center": [cx, cy],
                    "expected_max": [length / 2 + 1, gap_top / 2 + 1],
                    "tolerance": 1.0,
                    "feature_ref": feature_id,
                },
            ],
        )

    return result