"""Stepped bore helper: through-hole + counterbore/countersink with auto checks."""
from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from build123d import (
    Align,
    BuildPart,
    Cylinder,
    Location,
    Mode,
    Part,
)

from ..hardware.screws import Screw, screw

if TYPE_CHECKING:
    from .contract import ContractBuilder

BoreKind = Literal["counterbore", "countersink", "plain"]


def stepped_bore(
    spec: str | Screw,
    *,
    center: tuple[float, float] = (0.0, 0.0),
    through_depth: float = 10.0,
    bore_kind: BoreKind = "counterbore",
    fit: str = "normal",
    builder: ContractBuilder | None = None,
    feature_id: str = "stepped_bore",
) -> Part:
    """Create a stepped bore (through-hole + counterbore/countersink)."""
    s = screw(spec) if isinstance(spec, str) else spec
    cx, cy = center
    through_r = s.through_hole_diameter(fit) / 2

    parts: list[Part] = []

    with BuildPart(mode=Mode.PRIVATE) as through:
        Cylinder(radius=through_r, height=through_depth,
                 align=(Align.CENTER, Align.CENTER, Align.MIN))
    parts.append(through.part.moved(Location((cx, cy, 0))))

    recess_depth = 0.0
    if bore_kind == "counterbore" and s.head_diameter > 0:
        recess_r = s.counterbore_diameter() / 2
        recess_depth = s.counterbore_depth()
        with BuildPart(mode=Mode.PRIVATE) as recess:
            Cylinder(radius=recess_r, height=recess_depth,
                     align=(Align.CENTER, Align.CENTER, Align.MIN))
        parts.append(recess.part.moved(Location((cx, cy, through_depth))))
    elif bore_kind == "countersink" and s.head_diameter > 0:
        recess_depth = s.head_diameter / 2
        recess_r = s.head_diameter / 2
        with BuildPart(mode=Mode.PRIVATE) as recess:
            Cylinder(radius=recess_r, height=recess_depth,
                     align=(Align.CENTER, Align.CENTER, Align.MIN))
        parts.append(recess.part.moved(Location((cx, cy, through_depth))))

    result = parts[0]
    for p in parts[1:]:
        result = result.fuse(p)

    if builder is not None:
        checks: list[dict] = [
            {
                "id": f"{feature_id}_through",
                "type": "inner_diameter_at_z",
                "z": through_depth / 2,
                "center": [cx, cy],
                "expected": through_r * 2,
                "tolerance": 0.3,
                "feature_ref": feature_id,
            },
        ]
        if bore_kind == "counterbore" and recess_depth > 0:
            checks.append({
                "id": f"{feature_id}_recess",
                "type": "inner_diameter_at_z",
                "z": through_depth + recess_depth / 2,
                "center": [cx, cy],
                "expected": s.counterbore_diameter(),
                "tolerance": 0.3,
                "feature_ref": feature_id,
            })

        builder.add(
            feature={
                "id": feature_id,
                "description": f"{s.name} {bore_kind}, depth {through_depth}mm",
            },
            checks=checks,
        )

    return result
