# AgentCAD Workspace

You are working in an AgentCAD workspace. Your job is to create and refine CAD
models using the `agentcad` CLI and build123d geometry library.

## First Principles For CAD Agents

Your goal is not to produce a plausible-looking shape. Your goal is to turn the
user's intent into a CAD model whose important mechanical facts are measurable.

Before writing geometry, identify:

- functional surfaces: faces that mount, seal, slide, snap, support, or locate
- interfaces: holes, sockets, bosses, rails, lids, pins, gears, fasteners
- envelopes: keep-out volumes, tool access, insertion paths, external bounds
- failure modes: shallow holes, hidden collisions, edge breakouts, thin walls,
  detached ribs/tabs, wrong orientation, and unmeasured fits
- evidence: the checks, probes, sections, previews, and review gates that would
  catch each failure mode

Every meaningful feature should trace through this chain:

```text
user requirement -> feature in design.json -> concrete check -> measured result
```

If a feature cannot be checked yet, either add a check or explicitly record the
unknown before claiming the model is complete.

## Workflow (16 stages, do not skip)

1. **Understand**: read the user request, identify every feature, and pass the
   Discovery Gate. Capture functional surfaces, interfaces, envelopes,
   constraints, likely failure modes, and the evidence that will catch each
   one. Read `references/discovery.md` and write the Discovery table before
   choosing topology.
2. **Concept**: compare 2-3 topology concepts for non-trivial models. Choose
   the concept that can be validated with the clearest checks, not just the one
   that is easiest to draw. Read `references/concept-design.md`.
3. **Contract**: write `models/<name>/design.json` with features and checks. Read
   `references/contract-design.md`. Optionally add `param_ref` fields to checks
   for targeted fix suggestions on failure. Fill the feature evidence matrix
   (position, dimensions, access, wall/root, interface risk) before `part.py`.
4. **Suggest**: run `agentcad suggest-checks <name>` to find missing checks. Paste
   suggested templates into `design.json` after filling concrete values. Use
   `probe_plan` from the output to choose section/probe points.
5. **Params**: put tunable dimensions in `models/<name>/params.json`.
6. **Precheck**: run `agentcad precheck <name>`. Do not write `part.py` while
   precheck fails.
7. **Implement**: write `models/<name>/part.py` using build123d. The final object
   must be assigned to global variable `result`. Read
   `references/build123d-guide.md` for API patterns and
   `references/feature/index.md` for feature helpers. Consult
   `references/feature/hardware.md` for screw/nut/washer/insert dimensions.
8. **Build**: run `agentcad build <name>`. If it fails, read
   `references/debugging.md` for triage guidance. Read
   `references/cad-tdd.md` for the checks-first implementation loop.
9. **Measure**: run `agentcad measure <name>`.
10. **Render**: run `agentcad render <name> --views iso,front,top,side,back`.
    When section SVGs are generated, read the same-name `.json` analysis.
11. **Validate**: run `agentcad validate <name>`. It must pass. Read
   `references/validation-strategy.md` for check details, tolerances, and probe
   usage.
12. **Review**: run `agentcad review <name>` and inspect every `must_view`
    artifact.
13. **Preview**: run `agentcad preview <name>` (auto-opens browser; do NOT
    manually open the file). Use `--static` for offline HTML. See CLI Quick
    Reference for assembly and kind options.
14. **Quality Review**: apply `references/design-quality-review.md`. If the model
    is valid but not good, revise and repeat from the relevant stage.
15. **Deliver**: run `agentcad deliver <name>` only after review and quality
    review pass.
16. **Resume**: if interrupted, run `agentcad doctor <name>` for workflow state
    and recommended next command.

## Iteration Loop

When `agentcad validate` fails, use the iteration tools to converge:

1. Read the `checks` array in the JSON output. Each failing check includes a
   `suggested_fix` object with actionable guidance, `likely_source`
   (geometry/contract/artifact), and `next_commands` to investigate.
2. If `suggested_fix.confidence` is `"high"` and a `param` key is provided,
   update that param in `params.json` to the `suggested` value.
3. If `suggested_fix.confidence` is `"low"`, the param may not directly control
   the dimension. Inspect the check center/axis and the geometry before changing
   params. If `param_candidates` is present, try those params.
4. Run the `next_commands` from `suggested_fix` to inspect the geometry (probe,
   render section, measure) before making changes.
5. Re-run `agentcad validate <name>`.
6. Run `agentcad diff <name>` to see which checks were fixed, which regressed,
   and whether geometry drifted between iterations.

When validation passes but the model still looks wrong, do not just edit the
shape. First add or tighten the check that should have caught the issue, then
change geometry and validate again.

If you are unsure where you left off, run `agentcad doctor <name>` to get the
workflow state and the next recommended command.

## Model Variants

To create the same model with different dimensions:

1. Create a variant: `agentcad new <model>:<variant_name>`
2. Edit `models/<model>/variants/<variant_name>/params.json` with
   variant-specific dimensions.
3. Run any command with `<model>:<variant_name>` instead of `<model>`.

Variants share `part.py`, `design.json`, and `metadata.json`. Only `params.json`
differs. Variant outputs go to `models/<model>/outputs/<variant_name>/`.

## Hard Rules

- Units are millimeters unless the user explicitly says otherwise.
- Coordinate convention: +X right, +Y back, +Z up.
- Do not write generated artifacts outside `models/<name>/outputs/` or
  `assemblies/<name>/outputs/`.
- Do not manually export STEP/STL from `part.py`. The runner owns all exports.
- Do not create an assembly unless the user asks for multiple parts, fit,
  motion, enclosure/cover relationships, or another inter-model relationship.
- Treat `design.json` as the design contract: source of truth for intent.
  Treat CLI JSON output as the source of truth for actual state.
- Prefer structured geometry measurements over visual impressions. When a
  section SVG exists, read its same-name `.json` analysis before judging it.
- Every visible or functional feature must be represented in `design.json` and
  backed by at least one check that would fail if the feature were missing,
  misplaced, shallow, blocked, detached, or too thin.
- If visual review finds a problem, encode the problem as a check before or
  while fixing it. Do not rely on memory that you inspected it once.
- Do not claim a model is complete until `agentcad validate` and
  `agentcad review` both pass and the quality review has no blocking issues.
- Every requested feature must have at least one validation check.
- bbox + watertight alone are not sufficient: they pass even when features are
  missing or hidden.
- Prefer `agentcad.features` helpers when they match the requested primitive:
  helpers often emit design checks and metadata interfaces that are harder to
  forget by hand.
- Every hole needs a `min_clearance` check for each surrounding wall, adjacent
  solid, or relevant edge.
- Every hole also needs a `hole_accessibility` check on the real tool/fastener
  approach plane. Missing hole_accessibility is a blocking review gate.
- Every load-bearing attached feature needs at least one interface/root check
  in addition to a body-exists check. A lip, rib, boss, tab, wall, hook, or
  bracket arm that only touches at an edge is a blocker even if validate passes.
- Inspect side, front, top, back, and iso previews. A feature that looks
  detached in any orthographic view is not deliverable until the contract
  contains a check that would catch that failure.
- Reason edge-to-edge, never center-to-face.
- For multi-part products, validate fits in `assemblies/<name>/assembly.json`
  using component metadata references. Do not hand-copy anchors into assembly
  contracts when metadata can be referenced.
- `section_bbox_at_z` with `expected: "void"` must include a `region` field
  `[[x0,y0],[x1,y1]]` to avoid false passes on empty slices where the STL has
  no mesh at that Z.
- `min_wall_thickness` supports range mode: use `axis`, `range` `[start, end]`,
  `samples`, `region`, and `min_mm` instead of a single `z` plane.

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
    precheck.json       Static contract report
    review.json         Pre-delivery review report
    deliverable.json    Delivery manifest
    preview.html        Interactive preview (agentcad preview)
    <name>.step         STEP export
    <name>.stl          STL export

assemblies/<name>/
  assembly.json          Optional multi-model fit/mate contract
  outputs/
    assembly_geometry.json
    assembly_validation.json
    assembly_review.json
    preview.html          Interactive assembly preview
    <name>.mjcf.xml       MJCF verification artifact
```

## CLI Quick Reference

Append `:<variant>` to any model name to operate on a variant.

```bash
# Workspace and model setup
agentcad init <workspace> [--model <model>]
agentcad new <model>
agentcad new <model>:<variant>

# Build pipeline
agentcad precheck <model>
agentcad build <model>
agentcad build <model> --force
agentcad measure <model>
agentcad render <model>
agentcad render <model> --views iso,front,top,side,back
agentcad validate <model>

# Iteration and review
agentcad diff <model>
agentcad diff <model> --last
agentcad review <model>[:<variant>]
agentcad deliver <model>[:<variant>]

# Batch validation and regression
agentcad validate all                       # Validate all models and assemblies in workspace
agentcad validate all --models              # Only models
agentcad validate all --assemblies          # Only assemblies
agentcad validate all --include-variants    # Include model variants
agentcad validate all --fail-fast           # Stop after first failure
agentcad snapshot write                     # Write regression snapshots for all validated targets
agentcad snapshot write --target <name>     # Write snapshot for one target
agentcad snapshot write --target <model>:<variant>
agentcad snapshot compare                   # Compare current vs baseline snapshots
agentcad snapshot compare --target <name>   # Compare one target
agentcad snapshot compare --target <model>:<variant>

# Preview (auto-opens browser — do NOT manually run `open`)
agentcad preview <name>                  # Start local server + auto-open browser
agentcad preview <name> --static         # Self-contained HTML + auto-open browser
agentcad preview <name> --kind assembly  # Force assembly mode

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
agentcad probe <model> --plan
agentcad probe <model> --scan
agentcad probe <model> --scan --axis x
agentcad probe <model> --scan --axis y
agentcad render <model> --section-z <z>
agentcad render <model> --section-x <x>
agentcad render <model> --section-y <y>
agentcad inspect <model>
agentcad report <model>
agentcad doctor <model>[:<variant>]           # Workflow state diagnostics: gaps, next command
agentcad suggest-checks <model>               # Suggest missing checks based on design contract
agentcad clean [--model <name>] [--dry-run]   # Remove debug/history artifacts

# Assembly
agentcad assembly init <assembly>
agentcad assembly list
agentcad assembly validate <assembly>
agentcad assembly review <assembly>
```

All commands output machine-readable JSON by default. Read the JSON before
deciding the next action.
