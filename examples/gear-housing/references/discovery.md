# Discovery Gate

Run this before writing `models/<name>/design.json`.

Do not jump from a sparse request straight into geometry. First decide whether
the design intent is specified enough to build a measurable contract.

## When Discovery Is Blocked

Ask the user before writing `design.json` when any material choice is missing
or ambiguous:

- mating dimensions, envelope limits, hole sizes, mounting patterns, or
  interface standards
- manufacturing target, material, minimum wall thickness, or tolerance class
- load direction, orientation, handedness, keep-out zones, or assembly access
- feature priority when the user asks for alternatives or gives conflicting
  constraints
- any topology decision that would change the model, not just a parameter value

## How To Ask

- Use the harness's structured question tool when one exists. Otherwise ask
  directly in chat and stop.
- Ask 2-3 questions per round, not a long checklist.
- Offer concrete choices with a recommended default and the tradeoff for each
  choice.
- Ask only about what cannot be inferred from the request, existing
  `params.json`, references, or prior model files.
- If a choice changes the part topology, present 2-3 design directions and wait
  for the user's pick before committing the contract.

Example:

```text
I need two choices before writing the CAD contract:

1. Manufacturing target: FDM print (recommended for a fast prototype), CNC
   machining, or unknown/conservative?
2. Mounting interface: M4 clearance holes on the standard 40 mm square pattern,
   custom hole spacing, or no mounting holes?
```

## When You May Proceed

Proceed without waiting only when the missing detail is low-risk and can be
encoded as a conservative assumption. State the assumption and put the
measurable value in `params.json` and/or `design.json`.

Good assumptions:

- unspecified units -> millimeters
- unspecified general FDM clearance -> conservative 0.3-0.5 mm tolerance
- unspecified small fillet -> 1 mm if it does not affect mating geometry

Bad assumptions:

- hole spacing for an unknown mating part
- material or manufacturing process for a load-bearing part
- screw size or bolt-head clearance for assembly
- orientation of a directional port, duct, latch, or bracket
