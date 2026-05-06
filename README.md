# AgentCAD

AgentCAD is a CLI-first CAD workflow runtime for coding agents.

It provides a repeatable workspace, modeling rules, build/export tools,
measurement reports, previews, validation reports, and delivery manifests so an
agent can iterate on CAD models with measurable feedback.

## Current V0 Scope

- `cad new`: create a model folder with `part.py`, `params.json`, and `design.json`. Auto-initializes workspace if needed.
- `cad build`: execute build123d model code and export STEP/STL.
- `cad build`: execute build123d model code and export STEP/STL.
- `cad measure`: inspect STL geometry and write `geometry.json`.
- `cad render`: create a dependency-free SVG preview from STL.
- `cad validate`: run build, measure, render, and design checks.
- `cad deliver`: write a delivery manifest with generated artifacts.

## Install For Local Development With uv

```bash
uv sync
uv run cad --help
```

`build123d` is a required dependency. The repository pins Python 3.12 through
`.python-version` because the CAD backend depends on native geometry packages.

Without installing, run from source with:

```bash
PYTHONPATH=src python3 -m agentcad --help
```

## Quick Example

```bash
uv run cad new bracket --project /tmp/my-cad-project
cd /tmp/my-cad-project
uv run cad validate bracket --json
uv run cad deliver bracket --json
```

The default generated model is a simple build123d cuboid. Agent rules are
written into `AGENTS.md` and `skills/`.

## Current Status

See [docs/STATUS.md](docs/STATUS.md) for the latest implementation state,
validated 8025 fan adapter examples, lessons learned, and next recommended work.
