"""Hex panel helper: honeycomb-core lightweight panel."""
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
    Polygon,
    Rectangle,
    extrude,
)

from ._geometry import hexagon_vertices

if TYPE_CHECKING:
    from .contract import ContractBuilder


def _hex_grid_positions(
    width: float,
    depth: float,
    spacing: float,
) -> list[tuple[float, float]]:
    """Generate staggered hex grid positions within a bounding rectangle."""
    positions = []
    row_height = spacing * math.sin(math.radians(60))
    row_offset = spacing / 2
    row_idx = 0
    y = 0
    while y < depth + spacing:
        x_offset = row_offset if row_idx % 2 else 0
        x = x_offset
        while x < width + spacing:
            positions.append((x, y))
            x += spacing
        y += row_height
        row_idx += 1
    return positions


def hex_panel(
    size: tuple[float, float] | tuple[float, float, float],
    strut: float,
    spacing: float,
    *,
    frame: float | None = None,
    center: tuple[float, float] = (0.0, 0.0),
    base_z: float = 0.0,
    builder: ContractBuilder | None = None,
    feature_id: str = "hex_panel",
) -> Part:
    """Create a honeycomb-core lightweight panel.

    Builds a rectangular panel with hexagonal cells cut out, leaving
    only thin walls (struts) between cells and a solid frame border.

    Parameters
    ----------
    size : tuple
        (width, depth) for 2D size, or (width, depth, height) for 3D.
        Height defaults to ``strut`` if not provided.
    strut : float
        Hex cell wall thickness (mm). Also default panel height.
    spacing : float
        Center-to-center distance between hex cells (mm).
    frame : float or None
        Solid frame border width (mm). Default = strut.
    center : tuple[float, float]
        XY center position.
    base_z : float
        Z position of the base.
    builder : ContractBuilder | None
        If provided, registers feature and checks.
    feature_id : str
        Base ID for entries.

    Returns
    -------
    Part
        The honeycomb panel.
    """
    if len(size) == 2:
        width, depth = size
        height = strut
    elif len(size) == 3:
        width, depth, height = size
    else:
        raise ValueError(f"size must be (width, depth) or (width, depth, height), got {size}")

    if frame is None:
        frame = strut

    cx, cy = center

    # Hex cell inner radius (across-corners / circumradius)
    cell_r = (spacing - strut) / 2

    # Build solid panel first, then subtract hex cells
    with BuildPart(mode=Mode.PRIVATE) as bp:
        # Solid rectangular panel
        with BuildSketch():
            Rectangle(width, depth)
        extrude(amount=height)

        # Subtract hex cells at each grid position
        overshoot = 1.0
        grid = _hex_grid_positions(width, depth, spacing)
        hex_verts = hexagon_vertices(cell_r)

        for gx, gy in grid:
            # Only cut cells that are inside the panel bounds (with frame margin)
            if gx < -frame or gx > width + frame or gy < -frame or gy > depth + frame:
                continue
            if (gx < frame or gx > width - frame) and (gy < frame or gy > depth - frame):
                continue

            with BuildSketch(Plane(origin=(gx, gy, -overshoot / 2))):
                Polygon(hex_verts)
            extrude(amount=height + overshoot, mode=Mode.SUBTRACT)

    result = bp.part.moved(Location((cx, cy, base_z)))

    if builder is not None:
        builder.add(
            feature={
                "id": feature_id,
                "description": f"hex_panel {width}x{depth}x{height}mm strut={strut} spacing={spacing}",
            },
            checks=[
                {
                    "id": f"{feature_id}_bbox",
                    "type": "bbox_size",
                    "expected": [width, depth, height],
                    "tolerance": 1.0,
                    "feature_ref": feature_id,
                },
                {
                    "id": f"{feature_id}_volume",
                    "type": "volume_range",
                    "min": width * depth * height * 0.15,
                    "max": width * depth * height * 0.85,
                    "feature_ref": feature_id,
                },
            ],
        )

    return result