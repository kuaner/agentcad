# AgentCAD Design Document

## 1. Positioning

AgentCAD is an agent-first 3D/CAD modeling workflow runtime. It is not a
traditional CAD UI and not a desktop viewer. Its job is to give coding agents a
repeatable local environment for:

```text
model -> build -> measure -> render -> validate -> revise -> deliver
```

The user should be able to describe a part or assembly, then let a coding agent
create and refine the model with minimal manual interaction. Correctness should
come from measurable artifacts, not from visual intuition alone.

## 2. First Principles

### 2.1 Agents Already Write Code

The project should not compete with coding agents. Agents can already edit files
and run shell commands. AgentCAD provides the missing workflow runtime:

- a stable workspace protocol
- deterministic build/export commands
- structured error reports
- geometry measurements
- preview artifacts
- validation checks
- delivery manifests

### 2.2 CAD Correctness Must Be Observable

CAD is precise. A successful run should always produce machine-readable evidence:

- `build.json`
- `geometry.json`
- `validation.json`
- preview images
- STEP/STL artifacts
- `deliverable.json`

### 2.3 CLI First

The core interface is CLI, because coding agents, developers, and CI can all use
it. UI, MCP, and richer viewers are optional integrations, not V0 requirements.

## 3. Workspace Protocol

`cad init` creates:

```text
project/
  AGENTS.md
  cadproject.json
  skills/
    cad-workflow.md
    modeling-rules.md
    validation-rules.md
  models/
  references/
    images/
    notes.md
```

Each model owns its generated artifacts. V0 intentionally avoids a project-root
`outputs/` directory so agents have one unambiguous artifact location:

```text
models/<name>/
  README.md
  design.json
  params.json
  part.py
  outputs/
    build.json
    geometry.json
    validation.json
    preview.iso.svg
    <name>.step
    <name>.stl
    deliverable.json
```

## 4. Agent Workflow

Agents should follow:

```text
1. Read user requirements.
2. Create or update models/<name>/design.json.
3. Put tunable dimensions in params.json.
4. Implement geometry in part.py and assign the final object to result.
5. Run cad validate <name> --json.
6. Fix the first deterministic failure and rerun validation.
7. Run cad deliver <name> --json after validation passes.
```

Agents should not manually export STEP/STL from `part.py`; the runner owns
exports and reports.

## 5. Modeling Interface

V0 uses build123d source mode:

```text
models/<name>/part.py -> global result
models/<name>/params.json -> tunable values
models/<name>/design.json -> design intent and validation checks
```

`design.json` is a design contract, not a complete CAD IR. It records intent and
checks that can be evaluated after build:

```json
{
  "schema": "design-spec.v1",
  "model": "bracket",
  "units": "mm",
  "intent": "Rectangular sample block",
  "checks": [
    { "type": "bbox_size", "expected": [40, 30, 20], "tolerance": 0.2 },
    { "type": "watertight", "expected": true }
  ]
}
```

Future iterations may add a feature library or DSL only when repeated modeling
patterns justify it.

## 6. CLI Commands

V0 commands:

```bash
cad init <project>
cad new <model>
cad build <model> --json
cad measure <model> --json
cad render <model> --view iso --json
cad validate <model> --json
cad deliver <model> --json
```

All commands that agents call must support stable JSON output. Failures must also
be JSON and should include `stage`, `error.type`, `error.message`, and relevant
artifact paths.

## 7. V0 Implementation

V0 uses:

- build123d for CAD construction and STEP/STL export
- pure Python STL parsing for measurement
- dependency-free SVG preview rendering from STL
- JSON reports for build, geometry, validation, and delivery

The SVG renderer is intentionally modest. It gives agents and humans a preview
artifact without requiring Blender, Three.js, Playwright, or a GUI. PNG and
interactive viewers are future enhancements.

## 8. Iteration Plan

### V0: Minimal Agent Loop

Goal: an agent can create a model, build it, measure it, render it, validate it,
and produce a delivery manifest.

Scope:

- workspace scaffold
- model scaffold
- build123d runner
- STEP/STL export
- STL measurement
- SVG preview
- validation report
- delivery manifest

### V1: Stronger Geometry Observability

- topology report from CAD backend when available
- multiple previews: iso/front/top/side
- richer STL mesh statistics
- better build error extraction
- artifact hashes and stale detection

### V2: Design Spec Standardization

- formal JSON schema for `design.json`
- requirement ids and check ids
- spec-driven validation reports
- check coverage report
- human-readable validation summary

### V3: Feature Library

- high-level helpers for plate, boss, rib, slot, holes, patterns, fillets, and
  chamfers
- feature ids
- feature trace output
- validation checks that reference feature ids

### V4: Assemblies

- assembly workspace convention
- anchors and mate points
- clearance and collision checks
- optional MJCF/URDF export

### V5: CAD CI

- `cad validate all`
- regression snapshots
- batch model generation
- benchmark suites
- CI integration examples

## 9. Relationship To Forgent3D

Forgent3D is viewer-first: it pairs an interactive previewer with agent feedback
tools. AgentCAD is workflow-first: it gives coding agents a CLI runtime for
autonomous build/measure/validate/deliver loops.

The main lessons borrowed are:

- fixed project protocol
- agent instruction scaffolding
- system-owned export runner
- measurable geometry feedback
- preview artifacts
- iterative failure recovery

The main difference is that AgentCAD does not require a desktop UI or MCP server
in the core loop.
