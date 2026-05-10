# Design Quality Review

Use this after `agentcad validate` and `agentcad review` pass, before
`agentcad deliver`.

Validation answers "does it match the contract?" This review asks "is the
contract and resulting model good enough?"

## Inputs

Read:

- `models/<name>/design.json`
- `models/<name>/params.json`
- `models/<name>/concept.md` when present
- `models/<name>/outputs/geometry.json`
- `models/<name>/outputs/validation.json`
- `models/<name>/outputs/review.json`
- every SVG listed in `review.json.must_view`

## Scorecard

Score each category from 1-5. A score below 4 is a blocking issue unless the
user explicitly accepted that tradeoff.

| Category | What to check |
|---|---|
| Function | Does the geometry actually solve the user's job, not just match dimensions? |
| Assembly | Can fasteners, tools, cables, inserts, and mating parts reach their targets? |
| Manufacturability | Are wall thicknesses, overhangs, radii, clearances, and print/machining orientation realistic? |
| Structural logic | Is the load path supported by ribs, bosses, fillets, or material where needed? |
| Proportion | Does the part look intentionally proportioned rather than like joined boxes? |
| Simplicity | Is there avoidable geometry, extra mass, or needless topology? |
| Validation strength | Would the current checks catch a missing or misplaced critical feature? |

## Blocking Issues

Treat these as blockers:

- validate/review passed but an important user feature is not visible in the
  required SVGs
- any required orthographic preview is missing, especially `preview.side.svg`
- a feature appears detached, floating, edge-only connected, or structurally
  unsupported in any iso/front/top/side/back preview
- a screw hole lacks surrounding material, tool access, or realistic clearance
- a load-bearing transition has a sharp stress concentration with no fillet,
  rib, or thickness explanation
- a load-bearing attached feature lacks an explicit root/interface check in
  `design.json`
- feature checks are weak enough that the part could be wrong and still pass
- the concept promised a structural feature that the geometry does not include
- the model is a crude envelope when the request needed a usable mechanical part

## Required Review Note

Before delivery, write a short review note in the conversation:

```markdown
## Design Quality Review

- Function: 4/5, ...
- Assembly: 5/5, ...
- Manufacturability: 4/5, ...
- Structural logic: 4/5, ...
- Proportion: 4/5, ...
- Simplicity: 5/5, ...
- Validation strength: 4/5, ...

Blocking issues: none
Revisions made after review: ...
```

If there are blocking issues, revise the concept, `design.json`, `params.json`,
or `part.py`, then rerun precheck/validate/review before delivery.
