"""Screw hole helper: full parametric screw hole with clearance/tap options."""
from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from build123d import (
    Align,
    Cylinder,
    Locations,
    Mode,
)

from ..hardware.screws import Screw, screw
from .stepped_bore import SteppedBore

if TYPE_CHECKING:
    from .contract import ContractBuilder

HoleKind = Literal["clearance", "tap", "self_tap"]
HeadKind = Literal["counterbore", "countersink", "plain"]


class ScrewHole(SteppedBore):
    """Full parametric screw hole extending SteppedBore.

    Adds ``kind`` selection (clearance, tap, self-tap) and optional
    ``teardrop_angle`` for FDM-printable horizontal holes.

    Call ``cut()`` inside a ``with BuildPart()`` block to subtract
    the hole geometry.
    """

    def __init__(
        self,
        spec: str | Screw,
        *,
        center: tuple[float, float] = (0.0, 0.0),
        through_depth: float = 10.0,
        kind: HoleKind = "clearance",
        head: HeadKind = "counterbore",
        fit: str = "normal",
        teardrop_angle: float = 0.0,
        builder: ContractBuilder | None = None,
        feature_id: str = "screw_hole",
    ):
        s = screw(spec) if isinstance(spec, str) else spec

        # Map kind to through-hole radius
        if kind == "clearance":
            through_r = s.clearance_radius
        elif kind == "tap":
            through_r = s.tap_radius
        elif kind == "self_tap":
            through_r = s.nominal_diameter / 2 * 0.85
        else:
            raise ValueError(f"kind must be 'clearance', 'tap', or 'self_tap', got '{kind}'")

        bore_kind = head if head in ("counterbore", "countersink", "plain") else "plain"

        if head == "plain" or s.head_diameter == 0:
            bore_kind = "plain"

        super().__init__(
            s,
            center=center,
            through_depth=through_depth,
            bore_kind=bore_kind,
            fit=fit,
            builder=builder,
            feature_id=feature_id,
        )

        # Override through_r with the kind-specific value
        self.through_r = through_r
        self.hole_kind = kind
        self.teardrop_angle = teardrop_angle
        if builder is not None:
            # SteppedBore registers checks before ScrewHole applies kind-specific
            # tap/clearance sizing, so synchronize the contract to the final cut.
            for check in getattr(builder, "_checks", []):
                if check.get("id") == f"{feature_id}_through":
                    check["expected"] = self.through_r * 2
                elif check.get("id") == f"{feature_id}_access":
                    check["hole_diameter"] = self.through_r * 2

    def cut(self) -> None:
        """Subtract the screw hole from the active BuildPart context.

        If ``teardrop_angle > 0``, the through-hole is cut as a
        teardrop instead of a plain cylinder for FDM printability.
        """
        cx, cy = self.center
        overshoot = 1.0

        if self.teardrop_angle > 0:
            # Use teardrop for the through-hole
            from .teardrop import teardrop
            td = teardrop(
                diameter=self.through_r * 2,
                height=self.through_depth + overshoot,
                angle=self.teardrop_angle,
                center=(cx, cy),
                base_z=-overshoot / 2,
            )
            from build123d import add
            add(td, mode=Mode.SUBTRACT)
        else:
            with Locations((cx, cy, -overshoot / 2)):
                Cylinder(
                    radius=self.through_r,
                    height=self.through_depth + overshoot,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                    mode=Mode.SUBTRACT,
                )

        # Head recess
        if self.recess_depth > 0 and self.recess_r > 0:
            with Locations((cx, cy, self.through_depth - self.recess_depth)):
                Cylinder(
                    radius=self.recess_r,
                    height=self.recess_depth + overshoot,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                    mode=Mode.SUBTRACT,
                )


def screw_hole(
    spec: str | Screw,
    *,
    center: tuple[float, float] = (0.0, 0.0),
    through_depth: float = 10.0,
    kind: HoleKind = "clearance",
    head: HeadKind = "counterbore",
    fit: str = "normal",
    teardrop_angle: float = 0.0,
    builder: ContractBuilder | None = None,
    feature_id: str = "screw_hole",
) -> ScrewHole:
    """Backward-compatible factory: returns a ScrewHole instance."""
    return ScrewHole(
        spec,
        center=center, through_depth=through_depth, kind=kind,
        head=head, fit=fit, teardrop_angle=teardrop_angle,
        builder=builder, feature_id=feature_id,
    )
