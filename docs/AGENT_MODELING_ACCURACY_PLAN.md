# Agent Modeling Accuracy Plan

Last updated: 2026-05-13

## Goal

Make CAD agents model more accurately by turning design intent into measurable
contracts. The core loop is:

```text
requirements -> discovery -> functional surfaces -> interfaces
             -> failure modes -> checks -> probes -> evidence -> repair
```

The project should avoid a second planning system. The smallest useful change
is to harden `design.json`, then reuse that data in `review`, `suggest-checks`,
`probe --plan`, feature helpers, and assembly validation.

## First Principles

Most CAD failures are not random geometry failures. They are missing facts:

- The feature exists, but its function was never translated into a check.
- The hole has a diameter check, but no tool access or edge-breakout check.
- The wall looks present, but no wall/root thickness evidence exists.
- The parts validate alone, but their assembly axes, clearances, or insertion
  paths are not checked.
- The agent repairs by guessing sections instead of probing the most
  informative plane.

Therefore the system must force every important feature to answer:

1. Where is it?
2. How large is it?
3. Can it be accessed, if it is an access path?
4. Is the wall/root strong enough, if it carries load?
5. Is the interface or assembly risk measured?

## Deliverables

### P0: Design Intent Schema v1

Extend `design.json` with structured optional fields:

```json
{
  "functional_surfaces": [
    {
      "id": "mount_face",
      "feature_id": "base_plate",
      "role": "mounting_face",
      "datum": "z_min",
      "normal": [0, 0, -1],
      "critical": true
    }
  ],
  "interfaces": [
    {
      "id": "m3_mount",
      "type": "fastener_clearance",
      "feature_ids": ["mounting_holes"],
      "access_axis": "z",
      "clearance_mm": 0.3,
      "failure_modes": ["hole_blocked", "edge_breakout"]
    }
  ],
  "failure_modes": [
    {
      "id": "edge_breakout",
      "mode": "edge_breakout",
      "severity": "high",
      "affects": ["mounting_holes"],
      "required_evidence": ["position", "dimensions", "access", "interface_risk"]
    }
  ]
}
```

Implementation:

- Validate these fields in `agentcad.contract`.
- Fold them into the feature evidence matrix.
- Add a review gate for design-intent lint.
- Let `suggest-checks` derive concrete checks from interface and failure-mode
  requirements.

Acceptance:

- A high-severity failure mode without required evidence blocks review.
- A fastener interface without access and clearance evidence blocks review.
- Invalid references to feature IDs are reported as schema issues.

### P1: Probe Planner v2

`agentcad probe <model> --plan` should rank the most informative probes and
write a reusable plan:

```bash
agentcad probe bracket --plan --run
```

Artifact:

```text
models/<name>/outputs/probes.json
```

Each planned probe should include:

- `information_gain`: high / medium / low
- `linked_feature`
- `linked_failure_mode`
- executable `commands`
- optional `expected`
- probe geometry: axis, section plane, center, point, region

Acceptance:

- Shallow hole -> hole-bottom / depth section.
- Edge breakout -> hole center to outer contour or clearance probe.
- Thin wall -> wall/root region probe.
- Suspended rib -> root attachment section.
- Assembly eccentricity -> axis or mate probe.

### P2: Failure-Mode Benchmark

Create a small benchmark/cookbook set driven by known failure modes:

```text
examples/cadbench/
  README.md
  shallow-hole/
  edge-breakout/
  thin-wall/
  suspended-rib/
  assembly-eccentricity/
```

Each case contains a prompt, expected contract fragments, and the check types
that should catch the failure.

Metrics:

- placeholder check ratio
- evidence coverage
- false-pass rate
- repair iteration count
- probe usefulness

Acceptance:

- The cookbook examples map each failure mode to concrete checks.
- Tests assert that these fixture contracts produce the expected evidence
  requirements and suggestions.

### P3: Risk-Aware ContractBuilder

Feature helpers should register risk metadata in addition to geometry checks.
Agents that use helpers should get strong contracts by default.

Helper expectations:

- `screw_hole`: position, diameter, access, edge clearance/interface risk.
- `mounting_pattern`: per-hole diameter/access, pattern position, edge risk.
- `rib`: thickness, root attachment, suspended-rib failure mode.
- `slot`: width and nearby wall risk.
- `tube/socket`: ID/OD, wall, mating clearance.
- `boss`: height/bore/root wall/access.

Acceptance:

- Helper-generated contracts emit position/access/wall evidence wherever the
  helper owns enough geometry to measure it.
- Helpers declare unresolved risks such as edge breakout as `failure_modes`, so
  `review` and `suggest-checks` force the agent to add model-specific clearance
  evidence instead of hiding the risk behind placeholders.
- Tests prove helpers emit `failure_modes` and link checks to features.

### P4: Assembly Interface Contract

Assemblies should validate interface facts, not only component presence.

Assembly contract extension:

```json
{
  "interfaces": [
    {
      "id": "lid_to_body_boss",
      "type": "cylindrical_mate",
      "part_a": "body",
      "feature_a": "body.interfaces.socket",
      "part_b": "lid",
      "feature_b": "lid.interfaces.pin",
      "axis_tolerance_mm": 0.2,
      "clearance_mm": 0.25,
      "insertion_axis": "z"
    }
  ]
}
```

Implementation:

- Convert assembly interfaces into measurable mate/check evidence.
- Review axis offset, radial clearance, axial engagement, and insertion path
  coverage.

Acceptance:

- Assembly eccentricity is reported as a specific interface failure.
- Missing radial clearance or coaxial evidence blocks assembly review.

## Developer Checklist

1. Add schema/lint for new intent fields.
2. Make feature evidence matrix consume interfaces and failure modes.
3. Add strict review gate for design intent and evidence coverage.
4. Add `probe --plan --run` with `probes.json`.
5. Add failure-mode cookbook fixtures and tests.
6. Add helper risk metadata emission.
7. Add assembly interface coverage review.
8. Run full tests and commit with a clean worktree.
