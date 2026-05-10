# AgentCAD Workspace

You are working in an AgentCAD workspace. Your job is to create and refine CAD
models using the `agentcad` CLI and build123d geometry library.

## Workflow (14 stages, do not skip)

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
12. **Preview**: open `models/<name>/outputs/preview.html` or run
    `agentcad preview <name>` to regenerate it. Use the interactive 3D view to
    inspect topology, section SVGs, geometry values, and failing checks. For an
    assembly, open `assemblies/<name>/outputs/preview.html` or run the same
    top-level `agentcad preview <name>` command.
13. **Quality Review**: apply `references/design-quality-review.md`. If the
    model is merely valid but not good, revise the concept, contract, or
    geometry and repeat validation.
14. **Deliver**: run `agentcad deliver <name>` only after review and quality
    review pass.

Do not manually export STEP/STL from `part.py`. The runner owns all exports.

## Iteration Loop

When `agentcad validate` fails, use the iteration tools to converge:

1. Read the `checks` array in the JSON output. Each failing check includes a
   `suggested_fix` object with actionable guidance.
2. If `suggested_fix.confidence` is `"high"` and a `param` key is provided,
   update that param in `params.json` to the `suggested` value.
3. If `suggested_fix.confidence` is `"low"`, the param may not directly control
   the dimension. Inspect the check center/axis and the geometry before changing
   params.
4. Re-run `agentcad validate <name>`.
5. Run `agentcad diff <name>` to see which checks were fixed, which regressed,
   and whether geometry drifted between iterations.

## Model Variants

To create the same model with different dimensions (e.g., different sizes for
different applications):

1. Create a variant: `agentcad new <model>:<variant_name>`
2. Edit `models/<model>/variants/<variant_name>/params.json` with variant-specific dimensions.
3. Build the variant: `agentcad build <model>:<variant_name>`
4. Variant outputs go to `models/<model>/outputs/<variant_name>/`.

Variants share the same `part.py`, `design.json`, and `metadata.json` from the
base model. Only `params.json` differs per variant.

Use `model:variant` syntax with any command that accepts a model name:
`agentcad validate bracket:small`, `agentcad preview bracket:small`,
`agentcad deliver bracket:small`.

## Fix Suggestions (param_ref)

To get targeted fix suggestions on failing checks, add an optional `param_ref`
field to checks in `design.json`:

```json
{
  "id": "hole_diameter",
  "type": "inner_diameter_at_z",
  "z": 2.5,
  "expected": 5.0,
  "tolerance": 0.3,
  "center": [0, 0],
  "param_ref": "hole_diameter"
}
```

When this check fails, `suggested_fix` will include the param name, its current
value, and a suggested value. Without `param_ref`, the fix suggestion provides
a generic action string with actual vs expected values.

## SVG Previews

SVG previews now include dimension annotations: axis labels, dimension lines
with mm values, and a scale bar. The `preview.html` page shows SVG thumbnails
in a grid — click any thumbnail to open it in a modal overlay for detailed
inspection.

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
- Do not write generated artifacts outside `models/<name>/outputs/` or
  `assemblies/<name>/outputs/`.
- Do not create an assembly unless the user asks for multiple parts, fit,
  motion, enclosure/cover relationships, or another inter-model relationship.
  Assembly is optional and on-demand; preview is a universal review command.
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
  variants/<variant_name>/
    params.json  Variant-specific parameters
  outputs/
    build.json          Build report
    geometry.json       STL measurement report
    validation.json     Validation results
    validation-history/ Archived validation runs (for diff)
    observability.json  Aggregate previews, scans, and section measurements
    preview.html        Interactive local Three.js preview page
    precheck.json       Static contract report
    review.json         Pre-delivery review report
    deliverable.json    Delivery manifest
    preview.iso.svg     SVG preview (with dimension annotations)
    section.z10.00.svg  Section preview
    section.z10.00.json Section measurement sidecar
    <name>.step         STEP export
    <name>.stl          STL export
  outputs/<variant>/    Variant-specific output directory

assemblies/<name>/
  assembly.json          Optional multi-model fit/mate contract
  outputs/
    assembly_geometry.json
    assembly_validation.json
    assembly_observability.json
    assembly_review.json
    preview.html          Interactive assembly preview
    preview.combined.iso.svg
    preview.exploded.iso.svg
    <name>.mjcf.xml       MJCF verification artifact
```

## CLI Quick Reference

```bash
# Workspace and model setup
agentcad init <workspace> [--model <model>]
agentcad new <model>
agentcad new <model>:<variant>

# Build pipeline
agentcad precheck <model>
agentcad build <model>
agentcad build <model> --force
agentcad build <model>:<variant>
agentcad measure <model>
agentcad render <model>
agentcad render <model> --views iso,front,top,side,back
agentcad validate <model>
agentcad validate <model>:<variant>

# Iteration and review
agentcad diff <model>
agentcad diff <model> --last
agentcad review <model>
agentcad deliver <model>
agentcad deliver <model>:<variant>

# Preview
agentcad preview <name>
agentcad preview <name>:<variant>
agentcad preview <name> --kind model
agentcad preview <name> --kind assembly

# Inspection
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

# Assembly
agentcad assembly init <assembly>
agentcad assembly list
agentcad assembly validate <assembly>
agentcad assembly review <assembly>
```

All commands output machine-readable JSON by default. Read the JSON before
deciding the next action.
