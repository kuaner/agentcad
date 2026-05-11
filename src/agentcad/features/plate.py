"""Plate helper: flat plate with optional fillets, auto-emitting checks."""
from __future__ import annotations

from typing import TYPE_CHECKING

from build123d import Align, Box, BuildPart, Mode, Part
from build123d import fillet as _fillet

if TYPE_CHECKING:
    from .contract import ContractBuilder


def plate(
    width: float,
    depth: float,
    thickness: float,
    *,
    fillet_r: float = 0.0,
    builder: ContractBuilder | None = None,
    feature_id: str = "plate",
    bbox_tolerance: float = 0.5,
) -> Part:
    """Create a flat plate and optionally register bbox + watertight checks.

    Parameters
    ----------
    width : float
        X dimension (mm).
    depth : float
        Y dimension (mm).
    thickness : float
        Z dimension (mm).
    fillet_r : float
        Edge fillet radius (0 = sharp edges).
    builder : ContractBuilder | None
        If provided, registers a feature and matching checks.
    feature_id : str
        ID for the feature and check entries.
    bbox_tolerance : float
        Tolerance for bbox_size check.

    Returns
    -------
    Part
        The plate solid.
    """
    with BuildPart(mode=Mode.PRIVATE) as bp:
        Box(width, depth, thickness, align=(Align.CENTER, Align.CENTER, Align.MIN))
        if fillet_r > 0:
            _fillet(bp.edges(), radius=fillet_r)

    result = bp.part

    if builder is not None:
        checks: list[dict] = [
            {
                "id": f"{feature_id}_bbox",
                "type": "bbox_size",
                "expected": [width, depth, thickness],
                "tolerance": bbox_tolerance,
                "feature_ref": feature_id,
            },
        ]
        if fillet_r > 0:
            checks.append({
                "id": f"{feature_id}_watertight",
                "type": "watertight",
                "expected": True,
                "feature_ref": feature_id,
            })
        builder.add(
            feature={
                "id": feature_id,
                "description": f"plate {width}x{depth}x{thickness}mm",
            },
            checks=checks,
        )

    return result
