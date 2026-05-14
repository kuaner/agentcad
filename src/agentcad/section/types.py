from __future__ import annotations

# Axis constants match array index in 3D vertex tuples.
AXIS_X = 0
AXIS_Y = 1
AXIS_Z = 2

# 2D plane labels: (horizontal_axis_label, vertical_axis_label, plane_name)
_PLANE_LABELS: dict[int, tuple[str, str, str]] = {
    AXIS_X: ("Y (mm)", "Z (mm)", "YZ plane"),
    AXIS_Y: ("X (mm)", "Z (mm)", "XZ plane"),
    AXIS_Z: ("X (mm)", "Y (mm)", "XY plane"),
}
_AXIS_NAME = {AXIS_X: "X", AXIS_Y: "Y", AXIS_Z: "Z"}

Segment2D = tuple[tuple[float, float], tuple[float, float]]
