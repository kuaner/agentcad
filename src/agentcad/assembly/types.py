from __future__ import annotations

from dataclasses import dataclass

from ..stl import Vec3

ASSEMBLY_SCHEMA = "agentcad.assembly.v1"
GEOMETRY_SCHEMA = "agentcad.assembly.geometry.v1"
VALIDATION_SCHEMA = "agentcad.assembly.validation.v1"
OBSERVABILITY_SCHEMA = "agentcad.assembly.observability.v1"

EPS = 1e-6


class AssemblyError(Exception):
    def __init__(self, error_type: str, message: str):
        super().__init__(message)
        self.error_type = error_type
        self.message = message


@dataclass(frozen=True)
class Transform:
    translation: Vec3
    rotation_euler_deg: Vec3
    rotation: tuple[Vec3, Vec3, Vec3]
    matrix: list[list[float]]
