"""Sparse wall helper: lightweight rectangular infill wall."""
from __future__ import annotations

from typing import TYPE_CHECKING

from build123d import (
    Align,
    BuildPart,
    Box,
    Location,
    Mode,
    Part,
)

if TYPE_CHECKING:
    from .contract import ContractBuilder


def sparse_wall(
    size: tuple[float, float] | tuple[float, float, float],
    strut: float,
    spacing: float,
    *,
    center: tuple[float, float] = (0.0, 0.0),
    base_z: float = 0.0,
    builder: ContractBuilder | None = None,
    feature_id: str = "sparse_wall",
) -> Part:
    """Create a lightweight sparse infill wall.

    Builds a rectangular frame with vertical and horizontal struts
    forming a grid, leaving open cells between them. Simpler and
    more isotropic than ``hex_panel``.

    Parameters
    ----------
    size : tuple
        (width, depth) for 2D size, or (width, depth, height) for 3D.
        Height defaults to ``strut`` if not provided.
    strut : float
        Grid wall thickness (mm). Also default wall height.
    spacing : float
        Center-to-center distance between struts (mm).
    center : tuple[float, float]
        XY center position.
    base_z : float
        Z position of the base.
    builder : ContractBuilder or None
        If provided, registers feature and checks.
    feature_id : str
        Base ID for entries.

    Returns
    -------
    Part
        The sparse infill wall.
    """
    if len(size) == 2:
        width, depth = size
        height = strut
    elif len(size) == 3:
        width, depth, height = size
    else:
        raise ValueError(f"size must be (width, depth) or (width, depth, height), got {size}")

    cx, cy = center

    n_cols = max(1, round(width / spacing))
    n_rows = max(1, round(depth / spacing))
    col_sp = width / n_cols
    row_sp = depth / n_rows

    half_w = width / 2
    half_d = depth / 2
    half_h = height / 2

    with BuildPart(mode=Mode.PRIVATE) as bp:
        # Outer frame — 4 border struts
        # Top border
        Box(width, strut, height, align=(Align.CENTER, Align.MIN, Align.MIN),
            mode=Mode.ADD).moved(Location((0, half_d, 0)))
        # Bottom border
        Box(width, strut, height, align=(Align.CENTER, Align.MAX, Align.MIN),
            mode=Mode.ADD).moved(Location((0, -half_d, 0)))
        # Left border
        Box(strut, depth, height, align=(Align.MIN, Align.CENTER, Align.MIN),
            mode=Mode.ADD).moved(Location((-half_w, 0, 0)))
        # Right border
        Box(strut, depth, height, align=(Align.MAX, Align.CENTER, Align.MIN),
            mode=Mode.ADD).moved(Location((half_w, 0, 0)))

        # Vertical struts (columns)
        for i in range(1, n_cols):
            x = -half_w + i * col_sp
            Box(strut, depth - 2 * strut, height,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.ADD).moved(Location((x, 0, 0)))

        # Horizontal struts (rows)
        for j in range(1, n_rows):
            y = -half_d + j * row_sp
            Box(width - 2 * strut, strut, height,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.ADD).moved(Location((0, y, 0)))

    result = bp.part.moved(Location((cx, cy, base_z)))

    if builder is not None:
        builder.add(
            feature={
                "id": feature_id,
                "description": f"sparse_wall {width}x{depth}x{height}mm strut={strut} spacing={spacing}",
            },
            checks=[
                {
                    "id": f"{feature_id}_bbox",
                    "type": "bbox_size",
                    "expected": [width, depth, height],
                    "tolerance": 0.5,
                    "feature_ref": feature_id,
                },
                {
                    "id": f"{feature_id}_volume",
                    "type": "volume_range",
                    "min": width * depth * height * 0.10,
                    "max": width * depth * height * 0.70,
                    "feature_ref": feature_id,
                },
            ],
        )

    return result