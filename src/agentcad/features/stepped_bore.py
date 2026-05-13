"""Stepped bore helper: through-hole + counterbore/countersink with auto checks.

Usage within a BuildPart context::

    bore = SteppedBore("M4_cap", center=(10, 10), through_depth=8,
                       bore_kind="counterbore", builder=b, feature_id="hole_0")
    bore.cut()
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from build123d import (
    Align,
    BuildPart,
    Cone,
    Cylinder,
    Location,
    Locations,
    Mode,
    Part,
)

from ..hardware.screws import Screw, screw

if TYPE_CHECKING:
    from .contract import ContractBuilder

BoreKind = Literal["counterbore", "countersink", "plain"]


class SteppedBore:
    """Through-hole with optional counterbore/countersink.

    Call ``cut()`` inside a ``with BuildPart()`` block to subtract
    the bore geometry directly.
    """

    def __init__(
        self,
        spec: str | Screw,
        *,
        center: tuple[float, float] = (0.0, 0.0),
        through_depth: float = 10.0,
        bore_kind: BoreKind = "counterbore",
        fit: str = "normal",
        builder: ContractBuilder | None = None,
        feature_id: str = "stepped_bore",
    ):
        s = screw(spec) if isinstance(spec, str) else spec
        self.screw = s
        self.center = center
        self.through_depth = through_depth
        self.bore_kind = bore_kind
        self.through_r = s.through_hole_diameter(fit) / 2
        self.recess_depth = 0.0
        self.recess_r = 0.0
        self.cone = False

        if bore_kind == "counterbore" and s.head_diameter > 0:
            self.recess_r = s.counterbore_diameter() / 2
            self.recess_depth = s.counterbore_depth()
        elif bore_kind == "countersink" and s.head_diameter > 0:
            # Countersink uses a Cone for conical recess (90° included angle)
            self.recess_depth = s.head_diameter / 2
            self.recess_r = s.head_diameter / 2
            self.cone = True

        if builder is not None:
            cx, cy = center
            checks: list[dict] = [
                {
                    "id": f"{feature_id}_through",
                    "type": "inner_diameter_at_z",
                    "z": through_depth / 2,
                    "center": [cx, cy],
                    "expected": self.through_r * 2,
                    "tolerance": 0.3,
                    "feature_ref": feature_id,
                },
                {
                    "id": f"{feature_id}_access",
                    "type": "hole_accessibility",
                    "axis": "z",
                    "z": through_depth + 0.5,
                    "center": [cx, cy],
                    "hole_diameter": self.through_r * 2,
                    "clearance_diameter": max(s.head_diameter + 1.0, self.through_r * 2 + 1.0),
                    "feature_ref": feature_id,
                },
            ]
            if bore_kind == "counterbore" and self.recess_depth > 0:
                checks.append({
                    "id": f"{feature_id}_recess",
                    "type": "inner_diameter_at_z",
                    "z": through_depth - self.recess_depth / 2,
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
            builder.add_interface(f"{feature_id}_screw_axis", {
                "kind": "screw_axis",
                "axis": {"point": [cx, cy, 0], "direction": [0, 0, 1]},
                "clearance_diameter": self.through_r * 2,
                "screw": s.name,
            })
            builder.add_design_interface({
                "id": f"{feature_id}_fastener_interface",
                "type": "fastener_clearance",
                "feature_ids": [feature_id],
                "access_axis": "z",
                "failure_modes": ["hole_blocked", "edge_breakout"],
            })
            builder.add_failure_mode({
                "id": f"{feature_id}_edge_breakout",
                "mode": "edge_breakout",
                "severity": "high",
                "affects": [feature_id],
                "required_evidence": ["position", "dimensions", "access", "interface_risk"],
            })

    def cut(self) -> None:
        """Subtract the bore from the active BuildPart context.

        Must be called inside a ``with BuildPart()`` block.
        Uses ``Locations`` + ``Cylinder(mode=SUBTRACT)`` for reliable
        boolean cuts.
        """
        cx, cy = self.center
        overshoot = 1.0

        # Through-hole
        with Locations((cx, cy, -overshoot / 2)):
            Cylinder(
                radius=self.through_r,
                height=self.through_depth + overshoot,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT,
            )

        # Counterbore or countersink recess
        if self.recess_depth > 0 and self.recess_r > 0:
            recess_z = self.through_depth - self.recess_depth
            if self.cone:
                # Conical countersink: Cone(r1=through_r, r2=recess_r)
                with Locations((cx, cy, recess_z)):
                    Cone(
                        radius1=self.through_r,
                        radius2=self.recess_r,
                        height=self.recess_depth + overshoot,
                        align=(Align.CENTER, Align.CENTER, Align.MIN),
                        mode=Mode.SUBTRACT,
                    )
            else:
                # Cylindrical counterbore
                with Locations((cx, cy, recess_z)):
                    Cylinder(
                        radius=self.recess_r,
                        height=self.recess_depth + overshoot,
                        align=(Align.CENTER, Align.CENTER, Align.MIN),
                        mode=Mode.SUBTRACT,
                    )


def stepped_bore(
    spec: str | Screw,
    *,
    center: tuple[float, float] = (0.0, 0.0),
    through_depth: float = 10.0,
    bore_kind: BoreKind = "counterbore",
    fit: str = "normal",
    builder: ContractBuilder | None = None,
    feature_id: str = "stepped_bore",
) -> SteppedBore:
    """Backward-compatible factory: returns a SteppedBore instance."""
    return SteppedBore(
        spec,
        center=center, through_depth=through_depth, bore_kind=bore_kind,
        fit=fit, builder=builder, feature_id=feature_id,
    )
