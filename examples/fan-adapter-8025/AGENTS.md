# AgentCAD Workspace

You are working in an AgentCAD workspace.

## Goal

Create CAD models by editing files under `models/<name>/`, then use the `cad`
CLI to build, measure, render, validate, and deliver artifacts.

## Required Workflow

1. Create or update `models/<name>/design.json`.
2. Put tunable dimensions in `models/<name>/params.json`.
3. Implement geometry in `models/<name>/part.py`.
4. The final build123d object must be assigned to global variable `result`.
5. Run `cad validate <name> --json`.
6. If validation fails, fix the first deterministic failure and rerun.
7. Run `cad deliver <name> --json` only after validation passes.

## Rules

- Units are millimeters unless the user explicitly says otherwise.
- Do not manually export STEP/STL from `part.py`.
- Do not write generated artifacts outside `models/<name>/outputs/`.
- Treat `design.json` as the design contract.
- Treat CLI JSON output as the source of truth.
- Do not claim a model is complete until validation passes.
