# AgentCAD Assembly Technical Plan

Last updated: 2026-05-10

Status: V4 assembly validation is implemented beyond the original MVP. The
validator has AABB broad phase, mesh narrow-phase contact/penetration evidence,
descriptor-based inter-model clearance, assembly section checks, combined
assembly STL export, mandatory MJCF export, and a top-level interactive preview
command. External OCCT/MuJoCo browser runtimes remain optional viewers; they
are not the source of truth for AgentCAD validation.

Implemented CLI:

```bash
agentcad assembly init <assembly>
agentcad assembly list
agentcad assembly validate <assembly>
agentcad preview <assembly>
agentcad assembly review <assembly>
```

## 1. Goal

AgentCAD needs first-class assembly support without giving up its core principle:
CAD correctness should be decided by structured geometry evidence before visual
inspection.

The first assembly milestone should let an agent create, validate, and review
multi-model products such as a body/lid container, fan adapter plus screen
plate, or simple bolted interfaces. The system must answer questions like:

- Are the referenced parts present and freshly built?
- Do component anchors coincide after transforms?
- Are intended axes aligned or coaxial?
- Is the radial / axial clearance in tolerance?
- Do two components interfere?
- Is there enough engagement depth for a lid, pin, screw, or socket?
- Which preview and measurement artifacts should the agent inspect next?

Visual SVGs remain useful, but they are supporting evidence. The primary
assembly verdict comes from numeric geometry measurements.

## 2. Reference: Forgent3D Assembly Findings

The reviewed reference project at `/Users/kuaner/Documents/code/forgent3d`
implements assemblies through MJCF:

- Single rigid bodies live under `models/<part>/part.py`.
- Multi-part systems live under `models/<assembly>/asm.xml`.
- `asm.xml` references reusable part STL meshes through MJCF `<asset><mesh>`
  and `<geom type="mesh">`.
- Part-local anchors are emitted through `metadata.json`; assembly parameters
  copy those anchors into `params.json`.
- The build path validates XML shape, mesh references, path safety, and missing
  STL generation.
- The viewer applies MJCF body/geom transforms and can attempt MuJoCo
  simulation.

This is a strong preview and kinematic story, but it is not enough as
AgentCAD's canonical assembly contract:

- MJCF validation is mostly structural, not mechanical fit validation.
- Assembly geometry facts are limited; for example bbox is available, but mate
  residuals, inter-component clearance, and interference are not first-class.
- STL mesh references are practical for visualization but should not be the only
  representation of mechanical intent.
- Copying anchors from part metadata into assembly parameters creates drift
  risk.

AgentCAD should borrow the good parts: separate parts, named anchors, reusable
mesh artifacts, explicit body transforms, and MJCF as a required human-verifiable
assembly artifact. It should not make MJCF the source of truth for design
intent.

## 3. Design Principles

1. The canonical assembly contract is JSON, not MJCF.
2. Assembly validation must be deterministic and CLI-first.
3. Every mate or fit has a measurable residual.
4. Part metadata is referenced, not copied.
5. Component transforms are explicit and inspectable.
6. Rendering is downstream of measurement.
7. MJCF export is mandatory for human verification and dynamic preview.
8. glTF / OBJ are optional additional export formats.
9. A static solver should catch what it can before STL loading.

Occam rule for V4: implement the smallest system that can make a body/lid or
two-plate assembly pass or fail for the right geometric reason. Do not add a
general assembly DSL, motion solver, or broad export matrix before this works.

There are only three representations in the core loop:

- design intent: `assembly.json` and part `metadata.json`;
- measured geometry: transformed STEP/STL-derived facts;
- human verification artifact: generated MJCF.

A validation pass is trustworthy only when at least two of those representations
agree. Metadata alone is not enough, a mesh preview alone is not enough, and a
valid MJCF file alone is not enough.

## 4. Workspace Protocol

Add a project-level `assemblies/` directory:

```text
project/
  models/
    body/
      part.py
      params.json
      metadata.json
      outputs/
        body.step
        body.stl
    lid/
      part.py
      params.json
      metadata.json
      outputs/
        lid.step
        lid.stl
  assemblies/
    bit_holder/
      assembly.json
      outputs/
        assembly_geometry.json
        assembly_validation.json
        assembly_observability.json
        preview.combined.iso.svg
        preview.exploded.iso.svg
        bit_holder.mjcf.xml
        bit_holder.stl
```

`models/<name>/outputs/` remains the only artifact location for single parts.
Assembly artifacts live under `assemblies/<name>/outputs/`.

`cadproject.json` may optionally list assemblies for discovery:

```json
{
  "schema": "agentcad.project.v1",
  "assemblies": ["bit_holder"]
}
```

The CLI should also discover `assemblies/*/assembly.json` directly so this list
is not a hard dependency.

## 5. Canonical Assembly Schema

`assemblies/<assembly>/assembly.json` should be a typed contract:

```json
{
  "schema": "agentcad.assembly.v1",
  "name": "bit_holder",
  "units": "mm",
  "intent": "Body and lid assembly for a cylindrical bit holder.",
  "components": [
    {
      "id": "body",
      "model": "bit_holder_body",
      "transform": {
        "translation": [0, 0, 0],
        "rotation_euler_deg": [0, 0, 0]
      }
    },
    {
      "id": "lid",
      "model": "bit_holder_lid",
      "transform": {
        "translation": [0, 0, 80],
        "rotation_euler_deg": [0, 0, 0]
      }
    }
  ],
  "mates": [
    {
      "id": "lid_axis_coaxial",
      "type": "coaxial",
      "a": "body.interfaces.lid_neck.axis",
      "b": "lid.interfaces.recess.axis",
      "max_axis_angle_deg": 0.25,
      "max_radial_offset_mm": 0.05
    },
    {
      "id": "lid_step_engagement",
      "type": "axial_engagement",
      "a": "body.interfaces.lid_neck",
      "b": "lid.interfaces.recess",
      "min_mm": 4.0
    }
  ],
  "checks": [
    {
      "id": "lid_radial_clearance",
      "type": "radial_clearance",
      "inner": "lid.interfaces.recess.inner_cylinder",
      "outer": "body.interfaces.lid_neck.outer_cylinder",
      "min_mm": 0.15,
      "max_mm": 0.35
    },
    {
      "id": "no_body_lid_interference",
      "type": "interference_free",
      "components": ["body", "lid"],
      "tolerance": 0.05
    }
  ]
}
```

Paths like `body.interfaces.lid_neck.axis` are metadata references resolved from
the component model's `metadata.json`. They should not be duplicated into
`assembly.json`.

Transform rules for v1:

- `translation` is millimeters.
- `rotation_euler_deg` is XYZ order in degrees.
- Missing rotation means identity.
- Scale is not allowed. If a component needs a different size, rebuild the part
  with different parameters. Assembly-level scale can hide dimension mistakes
  and is therefore a false-pass risk.
- Internally every transform is canonicalized to a 4x4 matrix and written to
  `assembly_geometry.json`.

## 6. Part Metadata Contract

The current `agentcad.part.metadata.v1` should become stricter for
assembly-ready parts:

```json
{
  "schema": "agentcad.part.metadata.v1",
  "units": "mm",
  "anchors": {
    "origin": {"point": [0, 0, 0]},
    "lid_stop_top": {"point": [0, 0, 82], "normal": [0, 0, 1]}
  },
  "interfaces": {
    "lid_neck": {
      "kind": "cylindrical_male",
      "axis": {"point": [0, 0, 0], "direction": [0, 0, 1]},
      "outer_cylinder": {
        "type": "cylinder",
        "axis": "z",
        "center": [0, 0],
        "radius": 20.0,
        "z_range": [76.0, 82.0]
      }
    }
  }
}
```

Rules:

- Anchor coordinates are part-local, in the same frame as exported STEP/STL.
- Interfaces describe functional geometry, not renderer styling.
- Interface descriptors should reuse the existing shape descriptor vocabulary
  where possible: `box`, `cylinder`, `sphere`.
- Metadata may include derived dimensions, but those values must be generated
  from `part.py` parameters, not hand-maintained separately.
- Metadata descriptors used by an assembly must be checked against the built
  STL. A wrong `outer_cylinder.radius` in metadata must fail validation even if
  the assembly math is internally consistent.

## 7. Assembly Measurement Pipeline

`agentcad assembly measure <name>` should:

1. Load `assemblies/<name>/assembly.json`.
2. Resolve every component model.
3. Build stale component models through the existing `build_model` pipeline.
4. Load each component STL and `metadata.json`.
5. Apply component transforms to STL triangles and metadata primitives.
6. Emit component-level facts:
   - source model
   - source hash / build artifact path
   - transform matrix
   - local bbox
   - world bbox
   - triangle count
   - resolved anchors and interfaces
7. Verify metadata-to-geometry consistency for every referenced anchor and
   interface that has a measurable descriptor.
8. Emit assembly-level facts:
   - global bbox
   - component count
   - triangle count
   - pairwise bbox overlap
   - pairwise approximate clearance / interference
   - mate residuals
9. Write `assembly_geometry.json`.

Interference measurement uses layered evidence:

- broad phase: transformed component AABB overlap
- narrow phase: BVH-pruned triangle contact candidates, deterministic mesh
  samples, point-in-closed-mesh checks, maximum sampled penetration depth, and
  minimum sampled surface distance
- optional future acceleration: BREP or signed-distance kernels may improve
  speed/precision, but the validation contract already records enough evidence
  to avoid AABB-only false passes

Surface contact without inside samples is reported as contact evidence, not
solid interference. Real penetration is reported as negative clearance /
positive penetration depth and is checked by `interference_free`.

## 8. Assembly Checks

Initial check types:

| Check | Purpose |
|---|---|
| `component_exists` | Referenced model, STL, STEP, and metadata exist |
| `anchor_exists` | Metadata reference resolves |
| `interface_exists` | Interface reference resolves |
| `mate_coincident` | Two anchor points coincide within tolerance |
| `mate_axis_aligned` | Two axes are parallel within angular tolerance |
| `mate_coaxial` | Axis angle and radial offset are within tolerance |
| `interface_geometry_consistency` | Metadata interface descriptor matches measured component STL |
| `radial_clearance` | Inner radius minus outer radius is in range |
| `axial_engagement` | Overlap along an interface axis is above minimum |
| `inter_model_min_clearance` | Clearance between two transformed shape descriptors |
| `interference_free` | Component pair has no measured mesh interference |
| `component_pair_classified` | Every component pair is checked or explicitly ignored with reason |
| `mjcf_consistency` | Generated MJCF body/site transforms match `assembly_geometry.json` |
| `assembly_bbox_size` | Overall assembly envelope matches expectation |
| `assembly_section_component_count` | Transformed multi-component section has expected disconnected contours |

The checks should return the same shape as existing model checks:

```json
{
  "name": "lid_radial_clearance",
  "type": "radial_clearance",
  "ok": true,
  "actual_mm": 0.25,
  "min_mm": 0.15,
  "max_mm": 0.35,
  "components": ["body", "lid"],
  "evidence": {
    "outer_radius_mm": 20.0,
    "inner_radius_mm": 20.25
  }
}
```

## 8.1 Anti-False-Pass Gates

These gates are mandatory even if the user does not write them by hand in
`assembly.json`:

1. **Fresh component gate**: each component must have a successful current
   `build.json`, STL, STEP, and metadata artifact.
2. **Metadata geometry gate**: every referenced interface descriptor must be
   observed in the component STL within tolerance. For cylindrical interfaces,
   sample cross-sections along the declared axis and compare measured radius /
   diameter against metadata. For point/plane anchors, verify nearby material or
   void state when the descriptor declares one.
3. **Mate residual gate**: every entry in `mates` must emit a numeric residual;
   a mate that cannot be measured is a failure, not a warning.
4. **Fit coverage gate**: every fit-like mate must have both radial/lateral
   clearance and axial engagement/stop checks when those concepts apply.
5. **Component-pair gate**: every component pair must be covered by
   `interference_free`, `inter_model_min_clearance`, or an explicit ignore
   entry with a reason. Unclassified pairs fail review.
6. **Transform consistency gate**: the same canonical transform matrix must be
   used for STL triangles, metadata primitives, SVG rendering, and MJCF export.
7. **MJCF round-trip gate**: after export, parse the generated MJCF and compare
   body transforms, mesh paths, and site positions against
   `assembly_geometry.json`. A syntactically valid MJCF that does not match the
   measured assembly is a failure.

Design tolerances must be explicit in `assembly.json`. The implementation may
use a small numeric epsilon for floating point noise, but it must not invent
mechanical clearance tolerance on behalf of the user.

## 9. CLI Surface

Minimum V4 commands:

```bash
agentcad assembly init <assembly>
agentcad assembly list
agentcad assembly validate <assembly>
agentcad preview <assembly>
agentcad assembly review <assembly>
```

`validate` is the primary command. It owns measurement, rendering, MJCF export,
and consistency checks. The implementation may expose debug commands such as
`assembly measure`, `assembly render`, or `assembly export-mjcf`, but the MVP
should not require users or agents to call them separately.

Preview is deliberately not an assembly subcommand. It is a cross-cutting
review affordance for any generated CAD artifact. A model preview and an
assembly preview differ by source directory and payload shape, not by workflow
stage. `agentcad preview <name>` should auto-detect `models/<name>` versus
`assemblies/<name>`, with an explicit kind flag only for name collisions.

`assembly validate` should run measure first, then all assembly checks, then
render combined and exploded previews, then generate the MJCF verification
artifact and interactive `preview.html`. The command should fail if MJCF or
interactive preview generation fails, because the human review path must always
be available.

`assembly review` should block delivery when:

- any component lacks metadata,
- any declared mate lacks a numeric residual,
- any fit lacks both radial and axial checks,
- any component pair has unresolved interference,
- the MJCF verification artifact is missing or stale,
- visual artifacts are missing.

## 10. Observability Outputs

`assembly_observability.json` should aggregate:

- `components`: model, transform, bbox, artifact paths
- `mates`: residuals and pass/fail summary
- `relations`: pairwise component clearance / interference matrix
- `sections`: generated section SVGs and JSON sidecars
- `previews`: combined and exploded SVG paths
- `mjcf`: generated MJCF path, referenced mesh paths, body/site summary
- `summary`: component count, failing mate count, minimum clearance, warning count

This lets the agent answer "what should I look at next?" without parsing SVGs
first.

## 11. Rendering

Rendering is downstream of measurement:

- Combined preview: all transformed component triangles.
- Exploded preview: deterministic component offsets from assembly center, with
  the original transforms preserved in measurement JSON.
- Optional per-component colors in SVG for visual separation.
- Section previews should include component IDs in the JSON sidecar so a
  multi-component section can say which contour came from which model.

## 12. Required MJCF Verification Export

MJCF should be a required verification artifact, not the canonical assembly
source.

`agentcad assembly export-mjcf <assembly>` can convert:

- components -> `<body>`
- component STL assets -> `<asset><mesh>`
- anchors/interfaces -> `<site>`
- selected mates -> joints or equality constraints where the semantics are
  clear

This gives AgentCAD a path to dynamic / kinematic preview without requiring
every mechanical fit to be expressed in MJCF.

`agentcad assembly validate <assembly>` must call this exporter and include the
result in `assembly_validation.json` and `assembly_observability.json`.

The generated file should live at:

```text
assemblies/<assembly>/outputs/<assembly>.mjcf.xml
```

Minimum MJCF export requirements:

- one MJCF body per assembly component;
- one mesh asset per component STL;
- component transforms faithfully applied as MJCF body transforms;
- named sites for resolved anchors and interfaces;
- deterministic names so humans can cross-reference MJCF bodies/sites with
  `assembly.json`;
- no MJCF mesh `scale` in v1; all component dimensions must come from built part
  artifacts;
- an export summary listing body count, site count, mesh paths, and any mate
  semantics that could not be represented in MJCF.

The exporter must immediately parse the generated MJCF and produce an
`mjcf_consistency` result comparing:

- component/body count;
- component mesh paths;
- body translations/rotations;
- site world positions after applying body transforms;
- unresolved or dropped mate semantics.

If MuJoCo is available in an external viewer, a separate verification step can
add extra evidence:

- site world positions after MJCF loading;
- joint range and default pose sanity;
- equality constraint residuals;
- contact pairs during closed-pose simulation;
- motion sweep collision observations for articulated assemblies.

Those data are useful additional evidence, especially for mechanisms. They
still do not replace explicit AgentCAD checks such as radial clearance, axial
engagement, section component counts, descriptor clearance, and
interference-free component pairs.

Importing external MJCF should be treated as preview-only until it can be mapped
back to the JSON contract with measurable checks.

## 13. First E2E Target: Bit Holder Body + Lid

The body/lid example should become the first V4 acceptance fixture:

- Build `bit_holder_body` and `bit_holder_lid` as independent models.
- Each part emits interfaces:
  - body: `lid_neck.outer_cylinder`, `lid_stop_top`
  - lid: `recess.inner_cylinder`, `step_stop_bottom`
- Assembly checks:
  - body/lid axes coaxial
  - radial clearance in tolerance
  - axial engagement depth sufficient
  - lid stop contacts the intended shoulder plane
  - body and lid do not interfere in the closed pose
  - exploded and closed previews exist

Acceptance:

- `agentcad assembly validate bit_holder` passes.
- `assembly_geometry.json` exposes enough numbers for an LLM to explain why the
  fit is correct.
- `bit_holder.mjcf.xml` is generated and references both component meshes for
  human inspection.
- `<assembly>.stl` is generated from transformed component meshes for external
  viewers and slicers.
- Breaking the lid inner diameter or transform causes a deterministic failing
  check before visual review.

## 14. Implementation Phases

### Phase 1: Schema And Resolution

- Add `assemblies/` workspace discovery.
- Add parser and schema checks for `assembly.json`.
- Add metadata reference resolver.
- Add transform helpers for points, vectors, axes, boxes, cylinders, and STL
  triangles.
- Reject assembly-level scale and ambiguous transform fields.

### Phase 2: Measurement

- Build stale components.
- Load component STLs and metadata.
- Compute local/world bboxes and global bbox.
- Measure metadata-to-STL consistency for referenced interfaces.
- Write `assembly_geometry.json`.

### Phase 3: Validation Checks

- Add check registry for assembly checks.
- Implement mate and fit checks.
- Implement anti-false-pass gates.
- Implement mesh narrow-phase interference detection.
- Write `assembly_validation.json`.

### Phase 4: Rendering And Review

- Render combined/exploded SVGs.
- Generate mandatory MJCF verification artifact.
- Parse generated MJCF and compare it against assembly geometry output.
- Generate assembly observability JSON.
- Add assembly review gate.

### Phase 5: Example And Regression Tests

- Add bit-holder assembly fixture.
- Add tests for transform math, metadata resolution, mate residuals, clearance,
  and interference.
- Add one negative fixture for each critical failure:
  - missing anchor
  - axis offset
  - insufficient radial clearance
  - insufficient axial engagement
  - component interference

### Phase 6: Additional Export Adapters

- Add combined STL export.
- Add OBJ/glTF only if downstream human review needs those formats.
- Keep optional MuJoCo-backed verification metrics as external viewer evidence;
  AgentCAD validation remains CLI-first and numeric without requiring a browser
  runtime.

## 15. Open Questions

- Should assembly artifacts live under `assemblies/<name>/outputs/` or under a
  synthetic `models/<name>/outputs/` directory? This plan prefers
  `assemblies/` because assemblies are not single build123d parts.
- Should exact STEP assembly export be supported early? Initial scope should
  defer it; STL plus mandatory MJCF are enough for assembly review.
- How strict should metadata schema validation be for existing models? Likely
  warn first, then enforce for assembly-referenced models.
- Which narrow-phase interference method is accurate enough without pulling in a
  heavy geometry kernel? Start conservative and add acceleration only after
  fixtures show the need.
