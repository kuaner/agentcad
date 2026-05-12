"""Metadata interface schema validation and resolution.

Provides structured validation for the `interfaces` section of
`metadata.json`, enabling assembly contracts to reference and measure
component interfaces reliably.

Interface kinds:
  - cylindrical_male / cylindrical_female: a tube-like fit interface
  - screw_axis: a screw/bolt installation axis
  - dovetail_rail: a sliding dovetail rail
  - snap_pin / snap_socket: a snap-fit interface
  - gear_axis: a gear shaft axis
"""
from __future__ import annotations

from typing import Any

from .contract import SchemaIssue, _issue

# ── Constants ────────────────────────────────────────────────────────────────

VALID_INTERFACE_KINDS = frozenset({
    "cylindrical_male",
    "cylindrical_female",
    "screw_axis",
    "dovetail_rail",
    "snap_pin",
    "snap_socket",
    "gear_axis",
    "planar",
})


# ── Public API ────────────────────────────────────────────────────────────────


def validate_part_metadata_dict(metadata: Any) -> list[SchemaIssue]:
    """Validate metadata.json schema, focusing on interfaces and anchors."""
    if not isinstance(metadata, dict):
        return [_issue("", "metadata must be a JSON object")]
    issues: list[SchemaIssue] = []

    # Validate schema version.
    schema = metadata.get("schema")
    if schema is not None and str(schema) not in {
        "agentcad.part.metadata.v1",
    }:
        issues.append(_issue(
            "schema",
            f"unsupported metadata schema: {schema!r}",
            hint="Use 'agentcad.part.metadata.v1' or remove the schema field.",
        ))

    # Validate interfaces.
    interfaces = metadata.get("interfaces")
    if interfaces is not None:
        if not isinstance(interfaces, dict):
            issues.append(_issue("interfaces", "interfaces must be a JSON object"))
        else:
            for name, iface in interfaces.items():
                if not isinstance(iface, dict):
                    issues.append(_issue(
                        f"interfaces.{name}",
                        f"interface '{name}' must be a JSON object",
                    ))
                    continue
                issues.extend(_validate_interface(name, iface))

    # Validate anchors.
    anchors = metadata.get("anchors")
    if anchors is not None:
        if not isinstance(anchors, dict):
            issues.append(_issue("anchors", "anchors must be a JSON object"))
        else:
            for name, anchor in anchors.items():
                if not isinstance(anchor, dict):
                    issues.append(_issue(
                        f"anchors.{name}",
                        f"anchor '{name}' must be a JSON object",
                    ))
                    continue
                issues.extend(_validate_anchor(name, anchor))

    return issues


def _validate_interface(name: str, iface: dict[str, Any]) -> list[SchemaIssue]:
    """Validate a single interface entry."""
    path_prefix = f"interfaces.{name}"
    issues: list[SchemaIssue] = []

    kind = iface.get("kind")
    if not kind:
        issues.append(_issue(f"{path_prefix}.kind", "interface requires 'kind' field"))
        return issues
    kind_str = str(kind)
    if kind_str not in VALID_INTERFACE_KINDS:
        issues.append(_issue(
            f"{path_prefix}.kind",
            f"unknown interface kind: {kind_str!r}; valid: {sorted(VALID_INTERFACE_KINDS)}",
            hint=f"Did you mean one of: {sorted(VALID_INTERFACE_KINDS)}?",
        ))
        return issues

    # Axis is required for all kinds except planar.
    if kind_str != "planar":
        axis = iface.get("axis")
        if axis is None:
            issues.append(_issue(
                f"{path_prefix}.axis",
                f"interface kind '{kind_str}' requires an 'axis' field",
            ))
        elif isinstance(axis, dict):
            issues.extend(_validate_axis(axis, f"{path_prefix}.axis"))
        else:
            issues.append(_issue(f"{path_prefix}.axis", "axis must be a JSON object"))

    # Kind-specific validation.
    if kind_str in ("cylindrical_male", "cylindrical_female"):
        issues.extend(_validate_cylindrical_interface(iface, path_prefix, kind_str))
    elif kind_str == "screw_axis":
        issues.extend(_validate_screw_axis_interface(iface, path_prefix))

    return issues


def _validate_axis(axis: dict[str, Any], path: str) -> list[SchemaIssue]:
    """Validate an axis descriptor with point and direction."""
    issues: list[SchemaIssue] = []
    point = axis.get("point")
    if point is None:
        issues.append(_issue(f"{path}.point", "axis requires 'point' field"))
    elif not isinstance(point, list) or len(point) != 3:
        issues.append(_issue(f"{path}.point", "point must be [x, y, z]"))
    else:
        for i, val in enumerate(point):
            try:
                float(val)
            except (TypeError, ValueError):
                issues.append(_issue(f"{path}.point[{i}]", f"point[{i}] must be a number"))

    direction = axis.get("direction")
    if direction is None:
        issues.append(_issue(f"{path}.direction", "axis requires 'direction' field"))
    elif not isinstance(direction, list) or len(direction) != 3:
        issues.append(_issue(f"{path}.direction", "direction must be [dx, dy, dz]"))
    else:
        try:
            dx, dy, dz = float(direction[0]), float(direction[1]), float(direction[2])
            if abs(dx) < 1e-9 and abs(dy) < 1e-9 and abs(dz) < 1e-9:
                issues.append(_issue(f"{path}.direction", "direction must not be zero vector"))
        except (TypeError, ValueError):
            issues.append(_issue(f"{path}.direction", "direction values must be numbers"))

    return issues


def _validate_cylindrical_interface(
    iface: dict[str, Any], path_prefix: str, kind: str,
) -> list[SchemaIssue]:
    """Validate cylindrical interface shape descriptors."""
    issues: list[SchemaIssue] = []

    # Must have at least one cylinder descriptor.
    has_outer = "outer_cylinder" in iface
    has_inner = "inner_cylinder" in iface
    if not has_outer and not has_inner:
        issues.append(_issue(
            path_prefix,
            f"cylindrical interface '{kind}' requires outer_cylinder or inner_cylinder",
        ))
        return issues

    for key in ("outer_cylinder", "inner_cylinder"):
        desc = iface.get(key)
        if desc is not None:
            if isinstance(desc, dict):
                issues.extend(_validate_cylinder_descriptor(desc, f"{path_prefix}.{key}"))
            else:
                issues.append(_issue(f"{path_prefix}.{key}", f"{key} must be a JSON object"))

    return issues


def _validate_cylinder_descriptor(desc: dict[str, Any], path: str) -> list[SchemaIssue]:
    """Validate a shape descriptor that describes a cylinder."""
    issues: list[SchemaIssue] = []

    dtype = desc.get("type")
    if dtype != "cylinder":
        issues.append(_issue(f"{path}.type", f"expected type 'cylinder', got {dtype!r}"))

    axis = str(desc.get("axis", "z")).lower()
    if axis not in ("x", "y", "z"):
        issues.append(_issue(f"{path}.axis", f"axis must be x/y/z, got {axis!r}"))

    radius = desc.get("radius")
    if radius is None:
        issues.append(_issue(f"{path}.radius", "cylinder descriptor requires 'radius'"))
    else:
        try:
            r = float(radius)
            if r <= 0:
                issues.append(_issue(f"{path}.radius", "radius must be positive"))
        except (TypeError, ValueError):
            issues.append(_issue(f"{path}.radius", "radius must be a number"))

    center = desc.get("center")
    if center is not None and (not isinstance(center, list) or len(center) != 2):
        issues.append(_issue(f"{path}.center", "center must be [cx, cy] (or [cx, cz] for axis=y)"))

    range_key = f"{axis}_range"
    if range_key not in desc:
        issues.append(_issue(
            f"{path}.{range_key}",
            f"cylinder descriptor requires '{range_key}' for axis '{axis}'",
        ))
    elif not isinstance(desc[range_key], list) or len(desc[range_key]) != 2:
        issues.append(_issue(f"{path}.{range_key}", f"{range_key} must be [start, end]"))

    return issues


def _validate_screw_axis_interface(iface: dict[str, Any], path_prefix: str) -> list[SchemaIssue]:
    """Validate a screw_axis interface."""
    issues: list[SchemaIssue] = []

    clearance_diameter = iface.get("clearance_diameter")
    if clearance_diameter is None:
        issues.append(_issue(
            f"{path_prefix}.clearance_diameter",
            "screw_axis interface requires 'clearance_diameter'",
        ))
    else:
        try:
            cd = float(clearance_diameter)
            if cd <= 0:
                issues.append(_issue(
                    f"{path_prefix}.clearance_diameter",
                    "clearance_diameter must be positive",
                ))
        except (TypeError, ValueError):
            issues.append(_issue(
                f"{path_prefix}.clearance_diameter",
                "clearance_diameter must be a number",
            ))

    screw = iface.get("screw")
    if screw is not None:
        from .hardware.screws import screw as lookup_screw
        spec = str(screw)
        try:
            lookup_screw(spec)
        except KeyError:
            issues.append(_issue(
                f"{path_prefix}.screw",
                f"screw spec '{spec}' not found in hardware database",
                severity="warning",
                hint="Check agentcad.hardware.screws for valid specs.",
            ))

    return issues


def _validate_anchor(name: str, anchor: dict[str, Any]) -> list[SchemaIssue]:
    """Validate an anchor entry (a named reference point or plane)."""
    path_prefix = f"anchors.{name}"
    issues: list[SchemaIssue] = []

    point = anchor.get("point")
    if point is None:
        issues.append(_issue(f"{path_prefix}.point", "anchor requires 'point' field"))
    elif not isinstance(point, list) or len(point) != 3:
        issues.append(_issue(f"{path_prefix}.point", "point must be [x, y, z]"))

    direction = anchor.get("direction")
    if direction is not None:
        if not isinstance(direction, list) or len(direction) != 3:
            issues.append(_issue(f"{path_prefix}.direction", "direction must be [dx, dy, dz]"))

    return issues