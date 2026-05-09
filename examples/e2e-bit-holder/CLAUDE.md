# AgentCAD Workspace

You are working in an AgentCAD workspace. Your job is to create and refine CAD
models using the `agentcad` CLI and build123d geometry library.

## Workflow (13 stages, do not skip)

1. **Understand**: read the user request, identify every feature, and pass the
   Discovery Gate in `references/discovery.md`.
2. **Concept**: when the model is non-trivial, compare 2-3 topology concepts
   using `references/concept-design.md`. Commit to one concept before writing
   the contract.
3. **Contract**: write `models/<name>/design.json` with features and checks.
   Load `references/contract-design.md` before editing the contract.
4. **Params**: put tunable dimensions in `models/<name>/params.json`.
5. **Precheck**: run `agentcad precheck <name>`. Do not write `part.py` while
   precheck fails.
6. **Implement**: write `models/<name>/part.py` using build123d. The final
   object must be assigned to global variable `result`.
7. **Build**: run `agentcad build <name>`.
8. **Measure**: run `agentcad measure <name>`.
9. **Render**: run `agentcad render <name> --views iso,front,top,side,back`.
10. **Validate**: run `agentcad validate <name>`. It must pass.
11. **Review**: run `agentcad review <name>` and inspect every `must_view`
    artifact.
12. **Quality Review**: apply `references/design-quality-review.md`. If the
    model is merely valid but not good, revise the concept, contract, or
    geometry and repeat validation.
13. **Deliver**: run `agentcad deliver <name>` only after review and quality
    review pass.

Do not manually export STEP/STL from `part.py`. The runner owns all exports.

## Stage References

Read only the references needed for the current stage.

| Stage | Reference |
|---|---|
| Requirements, ambiguity, user choices | `references/discovery.md` |
| Topology options, tradeoffs, concept choice | `references/concept-design.md` |
| `design.json`, feature coverage, check selection | `references/contract-design.md` |
| Checks-first implementation loop | `references/cad-tdd.md` |
| Check details, tolerances, probe usage, validation failures | `references/validation-strategy.md` |
| build123d API patterns and geometry construction | `references/build123d-guide.md` |
| Build/debug triage and external docs lookup | `references/debugging.md` |
| Post-validation design quality critique | `references/design-quality-review.md` |

## Hard Rules

- Units are millimeters unless the user explicitly says otherwise.
- Coordinate convention: +X right, +Y back, +Z up.
- Do not write generated artifacts outside `models/<name>/outputs/`.
- Treat `design.json` as the design contract: source of truth for what the
  model should be.
- Treat CLI JSON output as the source of truth for what the model actually is.
- Prefer structured geometry measurements over visual impressions. When a
  section SVG exists, read its same-name `.json` analysis before judging it.
- Do not claim a model is complete until `agentcad validate` and
  `agentcad review` both pass and the quality review has no blocking issues.
- Every requested feature must have at least one validation check.
- bbox + watertight alone are not sufficient: they pass even when features are
  missing or hidden.
- Every hole needs a `min_clearance` check for each surrounding wall, adjacent
  solid, or relevant edge.
- Every hole also needs a `hole_accessibility` check on the real tool/fastener
  approach plane.
- Every load-bearing attached feature needs at least one interface/root check
  in addition to a body-exists check. A lip, rib, boss, tab, wall, hook, or
  bracket arm that only touches at an edge is a blocker even if validate passes.
- Inspect side, front, top, back, and iso previews. A feature that looks
  detached in any orthographic view is not deliverable until the contract
  contains a check that would catch that failure.
- Reason edge-to-edge, never center-to-face.

## Workspace Layout

```text
models/<name>/
  design.json    Feature contract: features list + checks
  params.json    Tunable dimensions
  part.py        build123d geometry (assign to `result`)
  metadata.json  (auto-generated if part.py defines `metadata`)
  outputs/
    build.json          Build report
    geometry.json       STL measurement report
    validation.json     Validation results
    observability.json  Aggregate previews, scans, and section measurements
    precheck.json       Static contract report
    review.json         Pre-delivery review report
    deliverable.json    Delivery manifest
    preview.iso.svg     SVG preview
    section.z10.00.svg  Section preview
    section.z10.00.json Section measurement sidecar
    <name>.step         STEP export
    <name>.stl          STL export
```

## CLI Quick Reference

```bash
agentcad init <workspace> [--model <model>]
agentcad new <model>
agentcad precheck <model>
agentcad build <model>
agentcad build <model> --force
agentcad measure <model>
agentcad render <model>
agentcad render <model> --views iso,front,top,side,back
agentcad validate <model>
agentcad review <model>
agentcad deliver <model>
agentcad probe <model> --z <z>
agentcad probe <model> --z <z> "--center=cx,cy"
agentcad probe <model> --z <z> --region x0,y0,x1,y1
agentcad probe <model> --x <x>
agentcad probe <model> --y <y>
agentcad probe <model> --z <z> --line-u <u>
agentcad probe <model> --z <z> --line-v <v>
agentcad probe <model> --z <z> --point u,v
agentcad probe <model> --x <x> --section-region u0,v0,u1,v1
agentcad probe <model> --scan
agentcad probe <model> --scan --axis x
agentcad probe <model> --scan --axis y
agentcad render <model> --section-z <z>
agentcad render <model> --section-x <x>
agentcad render <model> --section-y <y>
agentcad inspect <model>
agentcad report <model>
```

All commands output machine-readable JSON by default. Read the JSON before
deciding the next action.
