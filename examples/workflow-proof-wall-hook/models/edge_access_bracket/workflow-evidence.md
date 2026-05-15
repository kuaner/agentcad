# Workflow Evidence

This model is an end-to-end workflow proof, not a CADBench fixture. It was
created with `agentcad init` under `examples/workflow-proof-wall-hook`, using
the generated `AGENTS.md`/`CLAUDE.md` workflow.

## Intent

The part is a wall-mounted cable hook bracket with risks that should force the
workflow to produce measurable evidence:

- edge-adjacent M4 mounting holes
- fastener/tool access around those holes
- a cantilever hook arm with a load-bearing root
- a retaining lip that must be connected to the arm
- reinforcing ribs that must not be floating or too thin

## Workflow Findings

The first sparse contract produced concrete workflow pressure:

- `agentcad suggest-checks edge_access_bracket` returned 25 suggestions.
- `suggestion_quality.placeholder_count` was 60.
- The evidence matrix flagged missing access, interface/root, wall, and
  dimension evidence.
- The probe plan produced high-information edge, diameter, access, root, and
  wall probes tied to declared failure modes.

During the real geometry loop, `agentcad validate` exposed a workflow gap:
`section_bbox_at_z` templates and docs implied rectangular section dimensions
were valid, but the implementation only accepted `"solid"`/`"void"`. The fix
made `[width, depth]` a first-class expected value and used it for the hook arm
and retaining lip.

## Final Evidence

Final contract and geometry checks:

- `agentcad suggest-checks edge_access_bracket`: `suggestions: []`,
  `suggestion_quality.placeholder_count: 0`.
- `agentcad precheck edge_access_bracket`: passed; hole edge clearance is
  7.75 mm against a 6.0 mm minimum.
- `agentcad validate edge_access_bracket`: passed; measured bbox is
  `[64.0, 70.0, 18.0]`, watertight is true, hole access has zero blocking
  points, hook arm section is `[16.0, 40.0]`, and lip section is `[16.0, 5.0]`.
- `agentcad probe edge_access_bracket --plan --run`: passed and wrote
  `outputs/probes.json`.
- `agentcad review edge_access_bracket`: passed with `ready_to_deliver: true`.
- `agentcad preview edge_access_bracket`: generated `outputs/preview.html` and
  served it through the local HTTP preview server.
- `agentcad deliver edge_access_bracket`: generated the delivery manifest.

The generated outputs are intentionally left under `models/edge_access_bracket/outputs/`.
