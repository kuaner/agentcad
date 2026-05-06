from __future__ import annotations

import json


CADPROJECT_JSON = {
    "schema": "agentcad.project.v1",
    "units": "mm",
    "modelsDir": "models",
    "referencesDir": "references",
    "defaultBackend": "build123d",
}


AGENTS_MD = """# AgentCAD Workspace

You are working in an AgentCAD workspace.

## Goal

Create CAD models by editing files under `models/<name>/`, then use the `cad`
CLI to build, measure, render, validate, and deliver artifacts.

## Required Workflow

1. Convert the user request into a Feature Contract in `models/<name>/design.json`.
2. For every visible or functional feature, define at least one verification check.
3. Put tunable dimensions in `models/<name>/params.json`.
4. Implement geometry in `models/<name>/part.py`.
5. The final build123d object must be assigned to global variable `result`.
6. Run `cad validate <name> --json`.
7. If validation fails, fix the first deterministic failure and rerun.
8. Run `cad deliver <name> --json` only after validation passes.

## Rules

- Units are millimeters unless the user explicitly says otherwise.
- Do not manually export STEP/STL from `part.py`.
- Do not write generated artifacts outside `models/<name>/outputs/`.
- Treat `design.json` as the design contract.
- Treat CLI JSON output as the source of truth.
- Do not claim a model is complete until validation passes.
- Do not rely only on bbox/watertight checks. Each requested feature needs its
  own evidence.

## Verification Examples

- Holes: check count, diameter, spacing, and position when relevant.
- Sockets/tubes: check inner/outer diameter at defined Z sections and length.
- Chamfers/tapers: check section diameters at both ends and monotonic change.
- Clearances: check actual measured clearance or metadata-backed fit values.
- Assemblies: check anchors, joint axes, and clearance/collision constraints.
"""


SKILL_CAD_WORKFLOW = """# CAD Workflow

For every model:

```text
write feature contract -> edit params/source -> cad validate <name> --json -> fix -> repeat -> cad deliver <name> --json
```

Use `cad validate` as the main self-check command. It runs build, measurement,
preview rendering, and design checks.

Before editing geometry, list the required features in `design.json` and attach
verification checks to each feature. If a feature cannot be measured yet, add a
metadata-backed check and note the limitation in the feature description.
"""


SKILL_MODELING_RULES = """# Modeling Rules

- Source file: `models/<name>/part.py`.
- Parameters: `models/<name>/params.json`.
- Design contract: `models/<name>/design.json`.
- Final geometry variable: `result`.
- Optional metadata variable: `metadata`.
- Coordinate convention: +X right, +Y back, +Z up.
- Keep export logic out of model source.
- Use feature ids in `design.json` that match the intent of the geometry code.
- When implementing a taper/chamfer/socket, create geometry that changes the
  actual external or internal surface; adding overlapping solids is not enough.
"""


SKILL_VALIDATION_RULES = """# Validation Rules

Before completion:

1. `cad validate <name> --json` must return `ok: true`.
2. `outputs/geometry.json` must exist.
3. STEP/STL artifacts must exist unless the user requested a different format.
4. Preview artifacts must exist.
5. Every feature in `design.json.features` must have at least one check.
6. Design checks in `design.json` must pass or be explicitly marked out of scope.

Feature-to-check coverage is mandatory. A model that builds successfully but
lacks checks for requested features is incomplete.
"""


REFERENCE_NOTES = """# References

Put images, sketches, scan files, and user notes for this CAD project here.
"""


def model_readme(name: str) -> str:
    return f"""# {name}

AgentCAD model folder.

Edit:

- `design.json` for design intent and validation checks
- `params.json` for tunable dimensions
- `part.py` for build123d geometry

Generated artifacts for this model are written to this folder's `outputs/`
directory. The project root does not have a shared outputs directory in V0.
"""


def model_params() -> str:
    return json.dumps(
        {
            "length": 40.0,
            "width": 30.0,
            "height": 20.0,
        },
        indent=2,
    ) + "\n"


def model_design(name: str) -> str:
    return json.dumps(
        {
            "schema": "design-spec.v1",
            "model": name,
            "units": "mm",
            "intent": "Default rectangular sample block.",
            "features": [
                {
                    "id": "base_block",
                    "intent": "Rectangular solid block with parameter-driven envelope.",
                    "checks": ["bbox_size", "watertight"],
                }
            ],
            "checks": [
                {"id": "bbox_size", "type": "bbox_size", "expected": [40.0, 30.0, 20.0], "tolerance": 0.2},
                {"id": "watertight", "type": "watertight", "expected": True},
                {"type": "artifact_exists", "path": f"outputs/{name}.step"},
                {"type": "artifact_exists", "path": f"outputs/{name}.stl"},
            ],
        },
        indent=2,
    ) + "\n"


def model_part() -> str:
    return '''"""Default AgentCAD build123d model.

Tunable values live in params.json. The final geometry must be assigned to
global variable `result`.
"""
import json
from pathlib import Path

from build123d import *

PARAMS = json.loads((Path(__file__).with_name("params.json")).read_text(encoding="utf-8"))

length = float(PARAMS["length"])
width = float(PARAMS["width"])
height = float(PARAMS["height"])


def build():
    with BuildPart() as bp:
        add(Box(length, width, height))
    return bp.part


result = build()
metadata = {
    "schema": "agentcad.part.metadata.v1",
    "units": "mm",
    "anchors": {
        "origin": [0, 0, 0],
        "x_min": [-length / 2, 0, 0],
        "x_max": [length / 2, 0, 0],
    },
}
'''
