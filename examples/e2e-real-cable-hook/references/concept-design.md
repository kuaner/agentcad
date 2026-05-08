# Concept Design

Use this after discovery and before writing `design.json` for any non-trivial
part. The goal is to choose a good topology before the validation contract
locks the agent into a mediocre geometry.

Skip this only for simple primitives, direct dimension edits, or fixes where
the topology is already established.

## Required Output

Create a short concept note in the conversation before editing files. For
persistent work, also save it as `models/<name>/concept.md`.

The concept note must include:

1. User goal and operating context.
2. 2-3 topology concepts.
3. Tradeoffs for each concept.
4. Chosen concept and reason.
5. Key dimensions and assumptions that will become `params.json`.
6. Feature list and validation strategy that will become `design.json`.

## Topology Concepts

Each concept should describe the actual CAD structure, not just styling.

For each option, cover:

- load path and likely weak points
- assembly sequence and tool access
- manufacturing target and print/machining orientation
- minimum wall/rib assumptions
- support material or overhang risk for FDM
- which dimensions are mating-critical
- which checks will prove the concept works
- what would make the concept fail

Example:

```markdown
## Concept Options

### A. Single-piece plate with two raised bosses
- Best for: fast FDM prototype and simple screw mounting.
- Risk: bosses concentrate stress unless filleted and tied into ribs.
- Validation: bbox, boss positions, hole diameters, hole-wall clearance,
  bolt accessibility, min wall thickness around bosses.

### B. Folded L-bracket with triangular ribs
- Best for: higher bending stiffness under vertical load.
- Risk: more overhang and harder support removal.
- Validation: upright position, rib solids, transverse hole access,
  min wall thickness, section checks through both ribs.

### C. Two-piece clamp with captured nut pocket
- Best for: adjustable assembly.
- Risk: more parts and tighter tolerance stack-up.
- Validation: nut pocket void, screw path, clamp gap, clearance around tool.

Chosen: B, because the load is a cantilever and stiffness matters more than
print simplicity.
```

## When To Ask The User

Ask for a concept choice when multiple concepts satisfy the request but differ
in topology, assembly, manufacturing, cost, or visual form.

Use 2-3 options with a recommended default. Stop and wait for the answer unless
the user explicitly delegated design choice.

Proceed without asking only when one concept clearly dominates because of the
user's constraints. State why the other options were rejected.

## Concept Quality Bar

Before writing `design.json`, check the chosen concept:

- Can every important feature be validated with an existing check type?
- Are mating dimensions explicit or conservatively parameterized?
- Are holes accessible by fasteners/tools?
- Are wall thickness and clearances manufacturable?
- Is the load path plausible, not just visually plausible?
- Are there section views that will expose hidden mistakes?

If the answer is no, revise the concept or ask a focused question before
writing the contract.
