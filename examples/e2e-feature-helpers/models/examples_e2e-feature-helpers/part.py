"""Default AgentCAD build123d model.

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
