# AgentCAD Roadmap Execution Plan

Last updated: 2026-05-12

This document turns [`ROADMAP.md`](ROADMAP.md) into implementation-ready work.
It is written for future development sessions: each stage states the product
goal, design shape, affected modules, PR breakdown, test plan, and acceptance
criteria.

## Operating Model

### Delivery Rules

- Each stage should land as small PRs with a working CLI surface and tests.
- New commands must return stable JSON with `ok`, `stage`, and structured
  `error` fields on failure.
- Generated model artifacts remain under `models/<name>/outputs/`.
- Generated assembly artifacts remain under `assemblies/<name>/outputs/`.
- Project-level batch artifacts must not reintroduce ambiguous root-level model
  outputs. Use `.agentcad/` for project reports and snapshots.
- Any behavioral tightening that can make existing examples fail needs either a
  migration note or a transition warning first.

### Shared Payload Conventions

All new report payloads should use these common fields where applicable:

```json
{
  "ok": true,
  "stage": "stage_name",
  "project": "/abs/path",
  "generatedAt": "2026-05-12T00:00:00Z",
  "summary": {},
  "targets": [],
  "artifacts": {},
  "warnings": []
}
```

Target payloads should include:

```json
{
  "kind": "model",
  "name": "part_name",
  "variant": null,
  "ok": true,
  "durationMs": 1234,
  "artifacts": {},
  "checks": [],
  "warnings": []
}
```

Use `kind: "assembly"` for assemblies. For variants, use
`name: "model"` and `variant: "variant_name"` rather than encoding the colon in
the name.

### Test Strategy

For every PR:

- Unit-test pure discovery, normalization, diff, and schema logic.
- CLI-test the command surface and JSON shape.
- Fixture-test one representative workspace.
- Avoid slow full-CAD builds in the fast suite unless the fixture is small.
- Put heavy example validation in the `slow` marker or GitHub slow workflow.

---

## P0 — Batch Validation And Regression CI

### Product Goal

Make an entire AgentCAD workspace mechanically reviewable with one command.
After this stage, a maintainer should be able to ask: "Did this change alter
any supported model, variant, assembly, or validation result?" and get a
machine-readable answer.

### Design

Add workspace-level orchestration around existing model and assembly commands.
The first version should reuse existing validators instead of inventing a new
validation path.

Primary command:

```bash
agentcad validate all [--models] [--assemblies] [--include-variants] \
  [--include-slow] [--fail-fast] [--summary-only] [--output <path>]
```

Recommended default:

- validate models and assemblies
- skip variants unless `--include-variants` is passed
- continue after failures unless `--fail-fast` is passed
- write `.agentcad/validation/all.json`

Discovery order:

1. Resolve project root.
2. Discover `models/*/design.json`.
3. Discover variants under `models/<name>/variants/*/params.json`.
4. Discover `assemblies/*/assembly.json`.
5. Merge optional `cadproject.json` ordering if present.
6. Sort remaining filesystem targets by `(kind, name, variant)`.

Payload shape:

```json
{
  "ok": false,
  "stage": "validate_all",
  "summary": {
    "total": 12,
    "passed": 10,
    "failed": 2,
    "skipped": 0,
    "durationMs": 12345
  },
  "targets": [
    {
      "kind": "model",
      "name": "fan_duct_adapter_8025",
      "variant": null,
      "ok": true,
      "durationMs": 1000,
      "artifacts": {
        "validation": ".../validation.json"
      }
    }
  ],
  "artifacts": {
    "validation_all": ".../.agentcad/validation/all.json"
  }
}
```

### Affected Modules

- `src/agentcad/cli.py`: route `agentcad validate all` before model-name
  parsing.
- `src/agentcad/workspace.py`: target discovery helpers.
- `src/agentcad/validate.py`: batch orchestration entry point, or new
  `batch.py` if the module gets crowded.
- `src/agentcad/assembly.py`: expose a stable validate wrapper for batch use.
- `src/agentcad/jsonio.py`: reusable timestamp/report writing helpers if
  needed.
- `.github/workflows/ci.yml` and `slow-tests.yml`: add batch fixtures.

### Concrete Implementation

Add a new module unless `validate.py` remains readable:

```text
src/agentcad/batch.py
```

Use explicit records instead of passing loose tuples through the batch runner:

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class ValidationTarget:
    kind: str              # "model" | "assembly"
    name: str
    variant: str | None
    path: Path
    slow: bool = False

    @property
    def display_name(self) -> str:
        if self.variant:
            return f"{self.name}:{self.variant}"
        return self.name
```

Discovery functions:

```python
def discover_models(project: Path) -> list[ValidationTarget]:
    ...

def discover_variants(project: Path, model: str) -> list[ValidationTarget]:
    ...

def discover_assemblies(project: Path) -> list[ValidationTarget]:
    ...

def discover_validation_targets(
    project: Path,
    *,
    include_models: bool = True,
    include_assemblies: bool = True,
    include_variants: bool = False,
    include_slow: bool = False,
    changed_only: bool = False,
) -> list[ValidationTarget]:
    ...
```

Batch runner:

```python
def validate_all(
    project: Path,
    *,
    include_models: bool = True,
    include_assemblies: bool = True,
    include_variants: bool = False,
    include_slow: bool = False,
    fail_fast: bool = False,
    output: Path | None = None,
) -> dict:
    targets = discover_validation_targets(...)
    results = []
    for target in targets:
        result = validate_target(project, target)
        results.append(_target_summary(target, result))
        if fail_fast and not result.get("ok"):
            break
    payload = _batch_payload(project, targets, results)
    write_json(output or project / ".agentcad" / "validation" / "all.json", payload)
    return payload
```

Target validation dispatch should be deliberately boring:

```python
def validate_target(project: Path, target: ValidationTarget) -> dict:
    if target.kind == "model":
        return validate_model(project, target.name, variant=target.variant)
    if target.kind == "assembly":
        return validate_assembly(project, target.name)
    raise ValueError(f"unknown target kind: {target.kind}")
```

CLI parser detail:

- Keep `agentcad validate <model>` backward-compatible.
- Add optional flags to the existing `validate` subparser.
- In `dispatch`, branch on `args.model == "all"` before `_parse_model_target`.

```python
validate.add_argument("model")
validate.add_argument("--models", action="store_true")
validate.add_argument("--assemblies", action="store_true")
validate.add_argument("--include-variants", action="store_true")
validate.add_argument("--include-slow", action="store_true")
validate.add_argument("--changed-only", action="store_true")
validate.add_argument("--fail-fast", action="store_true")
validate.add_argument("--output", type=Path, default=None)
```

Interpretation:

- If neither `--models` nor `--assemblies` is passed, include both.
- If one is passed, include only the requested kind.
- `--changed-only` can start as a documented no-op returning
  `NotImplemented` if implementing Git-aware discovery would slow P0.2. Do not
  silently ignore it.

Project artifact layout:

```text
.agentcad/
  validation/
    all.json
  snapshots/
    models/
      fan_duct_adapter_8025.json
      l_bracket__variant_large.json
    assemblies/
      fan_with_screen.json
```

Target summary must strip huge nested payloads:

```python
def _target_summary(target: ValidationTarget, payload: dict) -> dict:
    return {
        "kind": target.kind,
        "name": target.name,
        "variant": target.variant,
        "ok": bool(payload.get("ok")),
        "stage": payload.get("stage"),
        "message": payload.get("message"),
        "checks": _check_summary(payload.get("checks") or []),
        "warnings": payload.get("warnings") or [],
        "artifacts": payload.get("artifacts") or {},
        "error": payload.get("error"),
    }
```

Do not embed full section analyses, full geometry payloads, preview HTML, or
STL-derived triangle data in `all.json`.

### PR Breakdown

#### P0.1 Target Discovery

Tasks:

- Add `discover_models(project)`.
- Add `discover_variants(project, model)`.
- Add `discover_assemblies(project)`.
- Add `discover_validation_targets(project, options)`.
- Normalize target records to `{kind, name, variant, path}`.

Tests:

- Empty workspace returns no targets.
- Model with `design.json` is discovered.
- Folder without `design.json` is ignored.
- Variant with `params.json` is discovered only when requested.
- Assembly with `assembly.json` is discovered.
- Sorting is deterministic.

Acceptance:

- Discovery does not run any CAD build.
- Discovery handles missing optional folders.

#### P0.2 CLI And Batch Runner

Tasks:

- Add `agentcad validate all`.
- Run model validation through existing `validate_model`.
- Run assembly validation through existing `validate_assembly`.
- Collect per-target results without throwing away structured errors.
- Implement `--fail-fast`.
- Write `.agentcad/validation/all.json`.

Tests:

- CLI returns `ok: true` when all fixture targets pass.
- CLI returns `ok: false` and exit code 1 when one target fails.
- `--fail-fast` stops after first failure.
- Output artifact path exists.
- Individual model/assembly outputs are still written in their normal
  locations.

Acceptance:

- Batch validation is a thin orchestrator over existing validators.
- The JSON shape is stable enough to be consumed by CI.

#### P0.3 Batch Fixtures And CI

Tasks:

- Choose a small fast fixture workspace.
- Mark larger real examples as slow.
- Add `uv run agentcad -p <fixture> validate all` to CI or slow CI.
- Document local command examples.

Tests:

- Fast fixture runs in normal CI.
- Slow fixture runs in `slow-tests.yml`.

Acceptance:

- CI catches a deliberately broken fixture when run locally.
- Slow tests remain manually/scheduled triggerable.

#### P0.4 Regression Snapshots

Tasks:

- Define `.agentcad/snapshots/<target>.json`.
- Normalize volatile fields out of snapshots:
  - timestamps
  - absolute paths
  - platform-specific temp paths
- Record stable metrics:
  - check IDs and status
  - bbox
  - volume
  - triangle count
  - artifact presence
  - selected section metrics
  - optional STL hash when stable
- Add compare mode:

```bash
agentcad snapshot write [--target <name>] [--all]
agentcad snapshot compare [--target <name>] [--all]
```

Alternative if command surface should stay small:

```bash
agentcad diff --snapshot <model>
agentcad validate all --compare-snapshots
```

Tests:

- Snapshot write strips volatile fields.
- Snapshot compare reports unchanged, changed, added, and removed checks.
- Numeric drift honors tolerances.
- Missing snapshot is a clear warning or failure depending on mode.

Acceptance:

- A helper geometry change produces a readable drift report.
- Snapshot format is documented and versioned.

Concrete snapshot module:

```text
src/agentcad/snapshot.py
```

Public functions:

```python
SNAPSHOT_SCHEMA = "agentcad.snapshot.v1"

def snapshot_target(project: Path, target: ValidationTarget, payload: dict) -> dict:
    ...

def write_snapshot(project: Path, target: ValidationTarget, payload: dict) -> Path:
    ...

def load_snapshot(project: Path, target: ValidationTarget) -> dict | None:
    ...

def compare_snapshot(current: dict, baseline: dict, *, tolerances: dict | None = None) -> dict:
    ...
```

Normalization rules:

```python
VOLATILE_KEYS = {
    "validatedAt",
    "builtAt",
    "measuredAt",
    "renderedAt",
    "observedAt",
    "generatedAt",
    "durationMs",
}
```

Normalize paths by keeping repository-relative paths when possible:

```python
def _relpath(project: Path, value: str) -> str:
    try:
        return str(Path(value).resolve().relative_to(project.resolve()))
    except Exception:
        return value
```

Snapshot shape:

```json
{
  "schema": "agentcad.snapshot.v1",
  "target": {"kind": "model", "name": "demo", "variant": null},
  "checks": {
    "bbox_size": {"type": "bbox_size", "ok": true, "actual": [40, 30, 20]},
    "watertight": {"type": "watertight", "ok": true}
  },
  "geometry": {
    "bbox_size": [40, 30, 20],
    "volume": 24000,
    "triangles": 12
  },
  "artifacts": {
    "step": true,
    "stl": true,
    "preview_iso": true
  }
}
```

Compare output:

```json
{
  "ok": false,
  "stage": "snapshot_compare",
  "target": {"kind": "model", "name": "demo", "variant": null},
  "changes": {
    "checks_regressed": [],
    "checks_fixed": [],
    "checks_added": [],
    "checks_removed": [],
    "geometry_drift": {
      "bbox_size_delta": [0, 0, 1.2],
      "volume_delta": 300.0,
      "triangles_delta": 24
    },
    "artifact_changes": []
  }
}
```

Initial tolerances should be explicit and conservative:

```python
DEFAULT_SNAPSHOT_TOLERANCES = {
    "bbox_abs_mm": 0.05,
    "volume_rel": 0.005,
    "triangles_abs": 0,
}
```

### Stage Acceptance

P0 is complete when:

- `agentcad validate all` works for models, variants, and assemblies.
- CI runs at least one batch validation fixture.
- Snapshot comparison exists for selected examples.
- A maintainer can review regression output without opening every artifact.

---

## P1 — Contract And Schema Hardening

### Product Goal

Make contracts harder to write incorrectly and easier for agents to fix.
False passes should become rare, and invalid contracts should fail before CAD
geometry is built.

### Design

Introduce lightweight internal schema validation without adding a heavy runtime
dependency unless necessary. The project already prefers standard Python and
structured JSON. Start with explicit validators that return field-path errors.

Error shape:

```json
{
  "type": "SchemaError",
  "message": "invalid design.json",
  "path": "checks[3].region",
  "hint": "section_bbox_at_z expected void requires region"
}
```

Schema versions:

- `design-spec.v1`
- `agentcad.part.metadata.v1`
- `agentcad.assembly.v1`
- `agentcad.validation.v1`
- `agentcad.review.v1`

### Affected Modules

- `src/agentcad/contract/schema.py`: design schema validation.
- `src/agentcad/contract/evidence.py`: feature evidence and design-intent lint.
- `src/agentcad/validate.py`: stricter check validation and warnings.
- `src/agentcad/precheck.py`: fail early on schema errors.
- `src/agentcad/review.py`: promote selected warnings to blocking gates.
- `src/agentcad/assembly/`: assembly and metadata schema checks.
- `src/agentcad/checks/section.py`: section semantics.
- `src/agentcad/checks/relations.py`: relation check validation.
- `tests/fixtures/` or `tests/test_contract_hardening.py`: negative fixtures.

### Concrete Implementation

Extend the `agentcad.contract` package without breaking existing callers that
expect check-shaped schema errors from the package root.

New issue type:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class SchemaIssue:
    path: str
    message: str
    issue_type: str = "SchemaError"
    severity: str = "error"  # "error" | "warning"
    hint: str | None = None

    def to_check(self, name: str = "design_schema") -> dict:
        payload = {
            "name": name,
            "type": "design_schema",
            "ok": self.severity != "error",
            "path": self.path,
            "severity": self.severity,
            "error": {"type": self.issue_type, "message": self.message},
        }
        if self.hint:
            payload["hint"] = self.hint
        return payload
```

Keep the old function name as a compatibility wrapper:

```python
def validate_design_schema_issues(design: dict[str, Any]) -> list[SchemaIssue]:
    ...

def validate_design_schema_dict(design: dict[str, Any]) -> list[dict]:
    return [issue.to_check() for issue in validate_design_schema_issues(design)]
```

Path helpers:

```python
def _issue(path: str, message: str, *, hint: str | None = None) -> SchemaIssue:
    return SchemaIssue(path=path, message=message, hint=hint)

def _check_path(index: int, field: str | None = None) -> str:
    return f"checks[{index}]" + (f".{field}" if field else "")
```

Check-specific schema validators:

```python
def _validate_section_bbox_check(check: dict, index: int) -> list[SchemaIssue]:
    issues = []
    expected = str(check.get("expected", "solid")).lower()
    if expected == "void" and "region" not in check:
        issues.append(SchemaIssue(
            path=_check_path(index, "region"),
            message="expected='void' requires region",
            severity="warning",
            hint="Add region [[x0,y0],[x1,y1]] so an empty global slice cannot pass accidentally.",
        ))
    return issues

def _validate_min_wall_thickness_check(check: dict, index: int) -> list[SchemaIssue]:
    has_single = "z" in check
    has_range = "range" in check and "axis" in check
    if not has_single and not has_range:
        return [_issue(_check_path(index), "min_wall_thickness requires z or axis+range")]
    return []
```

Feature classification should be deterministic and conservative:

```python
HOLE_WORDS = {"hole", "bore", "screw", "bolt", "fastener", "counterbore", "countersink"}
ATTACHMENT_WORDS = {"rib", "boss", "tab", "lip", "arm", "flange", "hook", "hinge"}
INTERFACE_WORDS = {"socket", "pin", "dovetail", "gear", "mate", "interface", "neck"}

def classify_feature(feature: dict, linked_checks: list[dict]) -> set[str]:
    text = " ".join(str(feature.get(k, "")) for k in ("id", "description", "intent")).lower()
    tags = set()
    if any(word in text for word in HOLE_WORDS):
        tags.add("hole")
    if any(word in text for word in ATTACHMENT_WORDS):
        tags.add("load_bearing_attachment")
    if any(word in text for word in INTERFACE_WORDS):
        tags.add("interface")
    return tags
```

Warning shape:

```json
{
  "feature": "base_holes",
  "category": "hole",
  "severity": "blocking",
  "missing": "hole_accessibility",
  "message": "hole-like feature has diameter checks but no access-envelope check",
  "suggested_check": {"type": "hole_accessibility", "...": "..."}
}
```

Transition switch:

- Implement strict behavior behind normal code paths, not environment flags.
- Use `severity` to transition:
  - first PR emits `warning`
  - later PR changes selected categories to `blocking`
- `review.py` decides whether `severity == "blocking"` affects `ok`.

### PR Breakdown

#### P1.1 Schema Error Infrastructure

Tasks:

- Add a small `SchemaIssue` structure.
- Add validators that return `list[SchemaIssue]`.
- Standardize error paths (`features[0].id`, `checks[2].expected`).
- Update CLI errors to include all issues, not just the first exception.

Tests:

- Missing required fields return field paths.
- Unknown check type returns a schema issue.
- Duplicate IDs return both duplicate locations when possible.
- Unsupported schema version fails explicitly.

Acceptance:

- Agents can tell exactly which field to edit.

#### P1.2 `section_bbox_at_z` Hardening

Tasks:

- Audit current behavior for `expected: "void"`.
- Add warning when no `region` is supplied.
- Add strict mode that fails missing region.
- Decide transition:
  - phase 1: warning in validate/review
  - phase 2: blocking in review
  - phase 3: blocking in validate

Tests:

- Empty slice without region does not falsely pass in strict mode.
- Explicit void region passes when region is actually void.
- Explicit void region fails when solid crosses region.
- Existing examples either pass or emit documented warnings.

Acceptance:

- Hollow models cannot accidentally pass because the section missed the mesh.

Implementation detail:

`evaluate_section_bbox_at_z` already rejects `expected='void'` without
`region`. Keep that post-build behavior. The missing piece is pre-build schema
feedback:

- `precheck` should surface the same issue before STL exists.
- `validate_design_schema_issues` should inspect check payloads by type.
- The issue path must be `checks[i].region`.

Do not change the existing region format:

```json
"region": [[x_min, y_min], [x_max, y_max]]
```

For X/Y sections later, add a new check type or an explicit `axis` field rather
than overloading `section_bbox_at_z`.

#### P1.3 `min_wall_thickness` Range Mode

Tasks:

- Extend check schema with:

```json
{
  "type": "min_wall_thickness",
  "axis": "z",
  "range": [0, 20],
  "samples": 11,
  "region": [[-10, -10], [10, 10]],
  "min_mm": 1.2
}
```

- Evaluate slices and report the worst result.
- Include `worst_plane`, `measured_mm`, and `sample_count`.

Tests:

- Passes when all slices exceed minimum.
- Fails when one slice is too thin.
- Handles empty slices with clear warning/error.
- Keeps existing single-plane behavior.

Acceptance:

- Thin-wall checks can cover real shells, not just one lucky plane.

Implementation detail:

Keep existing single-plane fields valid:

```json
{"type": "min_wall_thickness", "z": 3.0, "region": [[0,0],[10,10]], "min_mm": 1.0}
```

Add range mode:

```json
{
  "type": "min_wall_thickness",
  "axis": "z",
  "range": [0, 10],
  "samples": 6,
  "region": [[0, 0], [10, 10]],
  "min_mm": 1.0
}
```

Evaluation algorithm:

```python
def _sample_positions(start: float, end: float, samples: int) -> list[float]:
    if samples < 2:
        return [start]
    return [start + (end - start) * i / (samples - 1) for i in range(samples)]

def evaluate_min_wall_thickness_range(check: dict, ctx: CheckContext) -> dict:
    axis = _AXIS_BY_NAME[str(check.get("axis", "z")).lower()]
    positions = _sample_positions(...)
    samples = []
    for pos in positions:
        result = _evaluate_single_thickness(axis, pos, ...)
        samples.append(result)
    valid = [s for s in samples if s.get("ok")]
    worst = min(valid, key=lambda s: s["actual_mm"], default=None)
    return {
        "name": check_id,
        "type": "min_wall_thickness",
        "ok": bool(worst) and worst["actual_mm"] >= min_mm - tolerance,
        "axis": axis_name,
        "range": [start, end],
        "samples": samples,
        "worst_position": worst["position"] if worst else None,
        "actual_mm": worst["actual_mm"] if worst else None
    }
```

First implementation can support only `axis == "z"` if X/Y region semantics are
not ready. If so, schema must reject other axes with a clear message.

#### P1.4 Common-Error Negative Fixtures

Tasks:

- Add fixture builders for:
  - hole-wall interference
  - hole-to-edge break
  - hole-to-hole overlap
  - shallow through-hole
  - blocked tool access
  - detached lip/tab/rib
- Each fixture should be tiny and deterministic.
- Each test asserts the intended failure type and check ID.

Tests:

- One test per failure class.
- A passing control model for each class where practical.

Acceptance:

- The common-error catalog is enforced by tests, not just documentation.

#### P1.5 Weak-Check Review Gates

Tasks:

- Categorize features by names/descriptors:
  - holes
  - load-bearing attachments
  - interfaces
  - decorative/envelope features
- Emit targeted warnings.
- Promote high-confidence warnings to review blockers.

Tests:

- Declared hole without `hole_accessibility` is blocked.
- Rib/boss/tab without root/interface evidence warns or blocks.
- Non-hole cylinder is not incorrectly blocked.

Acceptance:

- Review output tells the agent what check is missing and why.

### Stage Acceptance

P1 is complete when:

- Schema errors are field-specific.
- Known false-pass patterns have negative tests.
- Section void semantics are no longer ambiguous.
- Weak-check warnings guide concrete next edits.

---

## P2 — Assembly Productization

### Product Goal

Make assemblies reliable enough for real multi-part products, not just example
validation. Components should expose machine-readable interfaces, and assembly
contracts should measure those interfaces instead of trusting metadata.

### Design

Keep `assembly.json` as the canonical assembly contract. Tighten
`metadata.json` so components can publish interfaces in a reusable way.

Recommended metadata interface shapes:

```json
{
  "interfaces": {
    "lid_neck": {
      "kind": "cylindrical_male",
      "axis": {"point": [0, 0, 0], "direction": [0, 0, 1]},
      "outer_cylinder": {
        "type": "cylinder",
        "axis": "z",
        "center": [0, 0],
        "radius": 20,
        "z_range": [76, 82]
      }
    },
    "m3_install": {
      "kind": "screw_axis",
      "axis": {"point": [10, 0, 4], "direction": [0, 0, 1]},
      "clearance_diameter": 8,
      "screw": "M3_cap"
    }
  }
}
```

Assembly checks should resolve references like
`body.interfaces.lid_neck.outer_cylinder` at validation time, apply component
transforms, and measure against built STL.

### Affected Modules

- `src/agentcad/assembly.py`: interface resolution, review gates.
- `src/agentcad/hardware/`: hardware-aware interface metadata.
- `src/agentcad/features/*`: optional interface emitters.
- `src/agentcad/features/contract.py`: metadata/interface accumulation if
  added.
- `tests/test_assembly.py`: additional fixtures.
- Example workspaces: `e2e-bit-holder`, `gear-housing`, and a new compact
  fastened-plate fixture if needed.

### Concrete Implementation

Add metadata validation and reference resolution in a focused module to keep
`assembly.py` from growing further:

```text
src/agentcad/metadata.py
```

Core structures:

```python
@dataclass(frozen=True)
class MetadataRef:
    component_id: str
    path: tuple[str, ...]  # ("interfaces", "lid_neck", "outer_cylinder")

@dataclass(frozen=True)
class ResolvedInterface:
    component_id: str
    name: str
    kind: str
    local: dict
    world: dict
```

Reference parsing:

```python
def parse_metadata_ref(value: str) -> MetadataRef:
    # "body.interfaces.lid_neck.outer_cylinder"
    parts = value.split(".")
    if len(parts) < 3:
        raise AssemblyError("MetadataRefInvalid", ...)
    return MetadataRef(component_id=parts[0], path=tuple(parts[1:]))
```

Validation functions:

```python
def validate_part_metadata_dict(metadata: dict) -> list[SchemaIssue]:
    ...

def validate_interface(name: str, interface: dict, path: str) -> list[SchemaIssue]:
    ...

def resolve_metadata_ref(ref: MetadataRef, components: dict[str, dict]) -> Any:
    ...

def transform_shape_descriptor(shape: dict, transform: Transform) -> dict:
    ...
```

Initial transform support should be honest:

- Axis-aligned shape descriptors with identity rotation: transform by
  translation.
- Axis-aligned descriptors with non-identity rotation: either support rotations
  that map axes exactly to X/Y/Z, or return `UnsupportedRotatedDescriptor`.
- Do not approximate rotated cylinders as axis-aligned unless the payload says
  it is an approximation.

Interface schema validators:

```python
def _validate_axis(axis: dict, path: str) -> list[SchemaIssue]:
    # requires point [x,y,z], direction [dx,dy,dz], nonzero direction

def _validate_cylinder_descriptor(desc: dict, path: str) -> list[SchemaIssue]:
    # type == "cylinder", axis in x/y/z, radius > 0, range length == 2

def _validate_screw_axis(interface: dict, path: str) -> list[SchemaIssue]:
    # screw string optional but if present must resolve in hardware.screws
    # clearance_diameter > 0
```

Assembly resolver integration:

- `_load_components` should read metadata and attach:

```python
record["metadata"] = read_json(model_dir(project, model) / "metadata.json", default={}) or {}
record["metadata_issues"] = validate_part_metadata_dict(record["metadata"])
```

- `validate_assembly` should convert metadata issues into checks:

```json
{
  "name": "metadata:body",
  "type": "metadata_schema",
  "ok": false,
  "issues": [...]
}
```

Helper metadata emission should not mutate files directly inside helpers.
Prefer extending `ContractBuilder` into a general design accumulator:

```python
class ContractBuilder:
    def add_interface(self, name: str, interface: dict) -> None: ...
    def to_metadata(self) -> dict: ...
    def write_metadata_to(self, project: Path, name: str, *, merge: bool = True) -> dict: ...
```

Keep `write_to()` behavior unchanged for `design.json`.

### PR Breakdown

#### P2.1 Metadata Interface Schema

Tasks:

- Validate `anchors` and `interfaces` in metadata.
- Support interface kinds:
  - `cylindrical_male`
  - `cylindrical_female`
  - `screw_axis`
  - `dovetail_rail`
  - `snap_pin`
  - `snap_socket`
  - `gear_axis`
- Reject malformed vectors, missing units, invalid radii, and unknown kinds.

Tests:

- Valid interface metadata passes.
- Unknown interface kind fails.
- Malformed axis fails with field path.
- Assembly validation fails if referenced interface is missing.

Acceptance:

- Assembly validation can rely on metadata shape, not ad hoc dictionaries.

#### P2.2 Helper-Emitted Interfaces

Tasks:

- Add optional metadata emission to selected helpers.
- Start with:
  - `tube` / `duct_socket` cylindrical interfaces
  - `screw_hole` screw axis
  - `snap_pin` and `snap_pin_socket`
  - `dovetail`
  - `spur_gear` / `ring_gear` axes
- Decide whether `ContractBuilder` should become `DesignBuilder` with metadata
  support or whether metadata stays separate.

Tests:

- Helper emits expected interface metadata.
- Interface metadata can be consumed by assembly validation.
- Re-running builder merge does not duplicate interfaces.

Acceptance:

- A simple assembly can be authored without hand-copying interface coordinates.

Concrete helper additions:

```python
def tube(..., builder: ContractBuilder | None = None, feature_id: str = "tube",
         interface_id: str | None = None, interface_kind: str = "cylindrical_male"):
    ...
    if builder and interface_id:
        builder.add_interface(interface_id, {
            "kind": interface_kind,
            "axis": {"point": [center_x, center_y, base_z], "direction": [0, 0, 1]},
            "outer_cylinder": {...},
            "inner_cylinder": {...}
        })
```

For `screw_hole`:

```json
{
  "kind": "screw_axis",
  "axis": {"point": [x, y, base_z], "direction": [0, 0, 1]},
  "screw": "M3_cap",
  "hole_diameter": 3.3,
  "clearance_diameter": 8.0,
  "install_axis": "z"
}
```

For `snap_pin` / `snap_pin_socket`:

```json
{
  "kind": "snap_pin",
  "axis": {"point": [x, y, z], "direction": [0, 0, 1]},
  "pin_diameter": 4.0,
  "engagement_length": 6.0
}
```

Tests should instantiate a helper, call `builder.write_metadata_to()`, then run
assembly reference resolution against that metadata. Do not only assert that a
dict was created.

#### P2.3 Assembly Fixture Expansion

Tasks:

- Add or refine fixtures:
  - body/lid cylindrical fit
  - snap pin/socket fit
  - gear/ring gear coaxial fixture
  - fastened plate with screw access
- Add intentionally broken variants:
  - radial offset
  - axial engagement too shallow
  - interference
  - missing pair coverage
  - stale component output

Tests:

- Passing fixtures validate.
- Broken fixtures fail for intended reason.
- Review blocks incomplete assemblies.

Acceptance:

- Assembly behavior is protected by fixtures that represent real product
  workflows.

#### P2.4 Assembly Review Gates

Tasks:

- Add explicit gates for:
  - missing metadata measurement
  - stale components
  - uncovered component pairs
  - missing preview/MJCF/combined STL
  - unmeasured declared interfaces
- Add `severity`: `info`, `warning`, `blocking`.

Tests:

- Each gate has one direct test.
- Review output includes next action command or fix hint.

Acceptance:

- `agentcad assembly review` is as useful as single-model `review`.

Concrete review check names:

```text
assembly_validation_present
assembly_validation_passed
artifact:geometry
artifact:mjcf
artifact:assembly_stl
artifact:preview_page
metadata_schema:<component_id>
interface_measured:<component_id>.<interface_name>
component_pair_classified:<a>:<b>
component_fresh:<component_id>
```

Severity policy:

- Missing validation, failed validation, missing geometry, missing MJCF, stale
  component, and uncovered component pair are blocking.
- Missing optional preview controls are warnings.
- Metadata schema errors are blocking only when the interface is referenced by
  the assembly contract; otherwise warnings.

### Stage Acceptance

P2 is complete when:

- Assembly-ready metadata has a schema.
- Helpers can emit common interfaces.
- Multiple assembly fixture types pass and fail for meaningful reasons.
- Review blocks incomplete assembly evidence.

---

## P3 — Agent Authoring UX

### Product Goal

Reduce the cognitive load on coding agents. The CLI should tell the agent what
to inspect, which check is missing, and which command should be run next.

### Design

Add an advisory layer that reads current project artifacts and produces
actionable guidance. Keep it deterministic: no LLM dependency, no heuristic that
mutates files automatically.

Primary command candidates:

```bash
agentcad doctor <model>
agentcad doctor <assembly> --kind assembly
agentcad suggest-checks <model>
```

`doctor` inspects the current state. `suggest-checks` focuses on missing
contract coverage.

### Affected Modules

- `src/agentcad/cli.py`: new commands.
- New `src/agentcad/doctor.py`: artifact and workflow diagnostics.
- New `src/agentcad/suggest/`: check suggestion engine.
- `src/agentcad/review.py`: reuse advisory rules where possible.
- Templates under `src/agentcad/_templates/workspace/references/`.
- Tests under `tests/test_doctor.py` and `tests/test_suggest.py`.

### Concrete Implementation

Doctor payload:

```json
{
  "ok": true,
  "stage": "doctor",
  "model": "demo",
  "state": "needs_validation",
  "findings": [
    {
      "id": "validation_missing",
      "severity": "blocking",
      "message": "validation.json is missing",
      "next_command": "agentcad validate demo"
    }
  ],
  "next_command": "agentcad validate demo"
}
```

State machine:

```python
WORKFLOW_STATES = (
    "missing_design",
    "needs_precheck",
    "needs_build",
    "needs_validation",
    "needs_review",
    "ready_for_delivery",
    "blocked",
)
```

Diagnostic rule shape:

```python
@dataclass(frozen=True)
class DoctorFinding:
    id: str
    severity: str       # "info" | "warning" | "blocking"
    message: str
    next_command: str | None = None
    artifact: str | None = None

def run_model_doctor(project: Path, name: str, variant: str | None = None) -> dict:
    artifacts = _model_artifact_state(project, name, variant)
    findings = []
    for rule in MODEL_DOCTOR_RULES:
        finding = rule(project, name, variant, artifacts)
        if finding:
            findings.append(finding)
    return _doctor_payload(...)
```

Initial model rules:

| Rule ID | Condition | Severity | Next command |
|---|---|---|---|
| `design_missing` | `design.json` missing | blocking | `agentcad new <model>` or edit design |
| `precheck_missing` | design exists but `precheck.json` missing | warning | `agentcad precheck <model>` |
| `build_missing` | STL/STEP missing | blocking | `agentcad build <model>` |
| `source_newer_than_build` | `part.py` or `params.json` newer than `build.json` | blocking | `agentcad build <model>` |
| `validation_missing` | `validation.json` missing | blocking | `agentcad validate <model>` |
| `validation_failed` | validation exists and `ok == false` | blocking | use failed check's `suggested_fix.next_commands[0]` |
| `review_missing` | validation passed but `review.json` missing | warning | `agentcad review <model>` |
| `preview_missing` | validation passed but `preview.html` missing | warning | `agentcad preview <model>` |

Suggestion engine:

```python
def suggest_checks(project: Path, name: str) -> dict:
    design = read_json(...)
    params = read_json(...)
    checks_by_feature = _index_checks(design)
    suggestions = []
    for feature in design.get("features", []):
        category = classify_feature(feature, checks_by_feature[feature_id])
        suggestions.extend(_suggest_for_category(feature, category, params, checks))
    return {"ok": True, "stage": "suggest_checks", "suggestions": suggestions}
```

Suggestion record:

```json
{
  "id": "base_holes.tool_access",
  "feature": "base_holes",
  "category": "hole",
  "priority": "high",
  "reason": "hole-like feature has diameter checks but no access check",
  "check_template": {
    "id": "base_holes_access",
    "type": "hole_accessibility",
    "axis": "z",
    "z": "<working_z>",
    "center": ["<x>", "<y>"],
    "hole_diameter": "<hole_diameter>",
    "clearance_diameter": "<tool_clearance_diameter>",
    "feature_ref": "base_holes"
  },
  "commands": [
    "agentcad probe <model> --z <working_z> --cx <x> --cy <y>"
  ]
}
```

Do not write suggestions into `design.json` automatically in the first version.
The command should be advisory and deterministic.

### PR Breakdown

#### P3.1 Doctor Command

Tasks:

- Inspect presence and freshness of:
  - `design.json`
  - `params.json`
  - `part.py`
  - `metadata.json`
  - `build.json`
  - `geometry.json`
  - `validation.json`
  - preview SVGs
  - `preview.html`
- Report next recommended command.
- Detect common workflow gaps:
  - design exists but no precheck
  - source changed after build
  - validation older than build
  - review missing after validation
  - previews missing

Tests:

- Fresh scaffold recommends precheck.
- Built but unvalidated model recommends validate.
- Validated but unreviewed model recommends review.
- Fully reviewed model reports ready state.

Acceptance:

- Agents can resume an interrupted workspace without manually inspecting files.

#### P3.2 Suggest Checks

Tasks:

- Read `design.json` features and existing checks.
- Suggest missing checks based on:
  - feature IDs/descriptions
  - check types already present
  - helper metadata if available
  - params names such as `hole`, `wall`, `rib`, `boss`, `socket`
- Return suggestions as JSON snippets, not direct edits.

Example suggestion:

```json
{
  "feature": "base_holes",
  "missing": "hole_accessibility",
  "reason": "hole-like feature has diameter checks but no tool envelope",
  "template": {
    "type": "hole_accessibility",
    "axis": "z",
    "center": ["<x>", "<y>"],
    "hole_diameter": "<diameter>",
    "clearance_diameter": "<tool_diameter>"
  }
}
```

Tests:

- Hole with diameter check but no access check gets suggestion.
- Envelope-only feature gets geometry-specific check suggestion.
- Non-hole cylinders are not classified as holes without evidence.

Acceptance:

- Suggestions are conservative and useful enough to paste into `design.json`
  after filling concrete values.

#### P3.3 Better Suggested Fix Payloads

Tasks:

- Add `next_commands` to failed checks.
- Add `likely_source`: `contract`, `geometry`, `artifact`, or `unknown`.
- Add parameter candidates when `param_ref` is absent but a param name is close.
- Include confidence values.

Tests:

- Failed bbox suggests param dimensions when obvious.
- Failed section check suggests probe/render command.
- Missing artifact suggests build/validate command.

Acceptance:

- A failed validation result contains the next CLI action for common failures.

Concrete payload extension:

```json
"suggested_fix": {
  "likely_source": "geometry",
  "confidence": "medium",
  "param_candidates": ["plate_w", "width"],
  "action": "increase plate_w or update bbox expected width",
  "next_commands": [
    "agentcad probe demo --scan --axis z",
    "agentcad render demo --view top"
  ],
  "evidence": {
    "type": "bbox_size",
    "actual": [39.2, 30.0, 20.0],
    "expected": [40.0, 30.0, 20.0]
  }
}
```

Mapping table:

| Check type | likely_source heuristic | next commands |
|---|---|---|
| `bbox_size` | geometry if actual exists, contract if expected implausible | `agentcad measure`, relevant `render --view` |
| `inner_diameter_at_z` | geometry | `agentcad probe --z ... --cx ... --cy ...` |
| `section_bbox_at_z` | geometry or contract if region missing | `agentcad render --section-z ...` |
| `min_clearance` | contract if design-time, geometry if post-build descriptor mismatch | `agentcad precheck` |
| `hole_accessibility` | geometry | `agentcad render --section-<axis> ...` |
| `artifact_exists` | artifact | command that creates missing artifact |

#### P3.4 Executable Helper Cookbook

Tasks:

- Store helper examples as testable snippets.
- Generate Markdown reference pages from snippets or keep snippets imported by
  tests.
- Cover common patterns:
  - screw holes and counterbores
  - standoffs and bosses
  - snap pin/socket
  - dovetail
  - gear pair
  - assembly interface metadata

Tests:

- Every cookbook snippet imports and builds.
- Snippets that emit contracts produce valid design checks.

Acceptance:

- Helper docs are not stale prose; they are backed by tests.

### Stage Acceptance

P3 is complete when:

- `doctor` can guide an agent through the workflow state.
- `suggest-checks` outputs useful conservative check templates.
- Failed validations point to next commands.
- Helper examples are executable and tested.

---

## P4 — Performance And Artifact Hygiene

### Product Goal

Keep batch validation fast and outputs manageable as the fixture set grows.

### Design

Add measurement first, then optimize the measured bottlenecks. Avoid changing
geometry semantics for speed.

### Affected Modules

- `src/agentcad/validate.py`: timing and stage reporting.
- `src/agentcad/section.py`: section extraction cache.
- `src/agentcad/render.py`: render timing and reuse.
- `src/agentcad/preview.py`: preview generation timing.
- New `src/agentcad/cleanup.py` if cleanup becomes a command.
- CI slow workflow for benchmarks.

### Concrete Implementation

Timing helper:

```python
from contextlib import contextmanager
from time import perf_counter

@contextmanager
def timed_stage(timings: dict[str, float], name: str):
    start = perf_counter()
    try:
        yield
    finally:
        timings[f"{name}Ms"] = round((perf_counter() - start) * 1000, 3)
```

Payload convention:

```json
"timings": {
  "buildMs": 1200.4,
  "measureMs": 34.2,
  "renderMs": 89.1,
  "checksMs": 56.8,
  "previewMs": 12.0,
  "totalMs": 1392.5
}
```

Do not replace existing `durationMs` in batch target summaries; batch can read
`timings.totalMs` and copy it into `durationMs`.

Section cache should be per validation run first:

```python
@dataclass(frozen=True)
class SectionCacheKey:
    stl_hash: str
    axis: int
    position: float

class SectionCache:
    def __init__(self, triangles: list[Triangle], stl_hash: str):
        self.triangles = triangles
        self.stl_hash = stl_hash
        self._segments: dict[SectionCacheKey, list] = {}
        self._analysis: dict[SectionCacheKey, dict] = {}

    def segments(self, axis: int, position: float) -> list:
        key = SectionCacheKey(self.stl_hash, axis, round(position, 5))
        if key not in self._segments:
            self._segments[key] = section_segments(self.triangles, axis, position)
        return self._segments[key]

    def analysis(self, axis: int, position: float) -> dict:
        key = SectionCacheKey(self.stl_hash, axis, round(position, 5))
        if key not in self._analysis:
            self._analysis[key] = analyze_section_segments(self.segments(axis, position), axis, position)
        return self._analysis[key]
```

Integration path:

- Add `section_cache` to `CheckContext` only if that does not disrupt tests.
- Otherwise keep `get_triangles()` unchanged and introduce helper functions in
  `checks/section.py` that optionally use cache from `ctx`.
- The first PR can instrument timings without cache; cache should be separate.

Cleanup command parser:

```bash
agentcad clean [target] [--kind model|assembly|auto] \
  [--validation-history] [--debug] [--previews] [--dry-run]
```

Deletion policy:

- `validation-history/*.json`: safe with retention.
- `debug.*.svg/json`: safe with retention.
- `preview.*.svg` and `preview.html`: delete only with `--previews`.
- STEP/STL/build/geometry/validation/deliverable: never delete in default clean.

### PR Breakdown

#### P4.1 Timing Instrumentation

Tasks:

- Add stage timings to build, measure, render, validate, preview, and assembly
  validation payloads.
- Include timings in batch validation summary.
- Keep output stable and numeric in milliseconds.

Tests:

- Payload includes nonnegative duration values.
- Timing fields do not break existing consumers.

Acceptance:

- Slow stages can be identified from JSON output.

#### P4.2 Section Cache

Tasks:

- Profile section-heavy examples.
- Cache triangle-plane intersections per STL hash, axis, and plane.
- Ensure cache invalidates when STL changes.
- Keep cache local to a validation run first; persistent cache can come later.

Tests:

- Cached and uncached section results match exactly.
- STL hash change invalidates cache.
- Repeated section checks call extraction fewer times.

Acceptance:

- Section-heavy validation is measurably faster with identical results.

Benchmark target:

- Use `examples/iphone15pro-case` as slow benchmark if build time is acceptable.
- Use a synthetic section-heavy cube/cylinder fixture in fast tests.
- Compare total calls to `section_segments` via monkeypatch in unit tests; do
  not rely only on wall-clock time in fast CI.

#### P4.3 Artifact Retention And Cleanup

Tasks:

- Define retention config:
  - validation history max count
  - debug artifact max age/count
  - preview regeneration policy
- Add optional cleanup command:

```bash
agentcad clean [--model <name>] [--validation-history] [--debug] [--dry-run]
```

- Never delete STEP/STL/deliverable artifacts unless explicitly requested.

Tests:

- Dry run reports deletions without deleting.
- Cleanup respects retention count.
- Protected artifacts are not removed.

Acceptance:

- Long-running workspaces do not accumulate unbounded debug artifacts.

#### P4.4 Benchmark Reporting

Tasks:

- Add slow CI benchmark command or mode.
- Track representative examples.
- Emit `.agentcad/benchmarks/latest.json`.
- Optionally compare against baseline with generous thresholds.

Tests:

- Benchmark command emits stable JSON.
- Missing baseline is handled cleanly.

Acceptance:

- Performance regressions are visible without making fast CI flaky.

### Stage Acceptance

P4 is complete when:

- Validation outputs include timings.
- Section-heavy examples are faster or at least measured.
- Artifact cleanup is safe and dry-run capable.
- Slow CI can publish benchmark JSON.

---

## P5 — Optional Integrations

### Product Goal

Expose AgentCAD to other tools only after the CLI and JSON contracts are stable.
Integrations should wrap proven operations, not create alternate truth paths.

### Design

Every integration should be a thin adapter over existing CLI-equivalent
functions. The JSON schemas from P1 should be treated as the integration
contract.

### Candidate Tracks

#### P5.1 MCP Server

Scope:

- Expose project discovery, precheck, validate, validate all, review, preview,
  and report.
- Return the same payloads as CLI commands.
- Avoid long-running hidden state; clients should receive artifact paths and
  structured results.

Acceptance:

- MCP validate result matches CLI validate result for the same target.
- Errors preserve `stage`, `error.type`, and `error.message`.

Concrete server shape:

Expose tool-equivalent functions, not a separate protocol:

```python
def mcp_precheck(project: str, model: str) -> dict: ...
def mcp_validate(project: str, target: str, kind: str = "auto") -> dict: ...
def mcp_validate_all(project: str, include_variants: bool = False) -> dict: ...
def mcp_review(project: str, target: str, kind: str = "auto") -> dict: ...
def mcp_report(project: str, model: str) -> dict: ...
```

Each should call the same Python functions used by CLI dispatch. Do not shell
out to `agentcad` unless packaging constraints require it.

#### P5.2 PNG / glTF Artifacts

Scope:

- PNG snapshots for CI comments or release artifacts.
- glTF export only if STL + HTML preview is insufficient for a real workflow.
- Keep SVG/JSON measurements as validation truth.

Acceptance:

- Optional artifacts never change validation verdicts.
- Missing optional renderer produces a clear skipped artifact, not a failed
  model validation unless explicitly required.

Concrete CLI shape:

```bash
agentcad export <target> --format png --view iso
agentcad export <target> --format gltf
```

Payload:

```json
{
  "ok": true,
  "stage": "export",
  "target": "demo",
  "format": "png",
  "artifacts": {"png": ".../outputs/preview.iso.png"}
}
```

Validation should only require these artifacts when a contract explicitly uses
`artifact_exists` for them.

#### P5.3 Template Gallery

Scope:

- Curate example workspaces by category:
  - brackets
  - ducts
  - enclosures
  - gears
  - assemblies
- Add `agentcad init --template <name>` only after examples are stable.

Acceptance:

- Templates are backed by batch validation snapshots.
- Template docs explain what checks protect the design.

### Stage Acceptance

P5 is complete when an integration has a real user workflow, uses stable
schemas, and does not bypass CLI validation semantics.

---

## Cross-Stage Workstreams

### Documentation

- Keep `ROADMAP.md` focused on priority and why.
- Keep this file focused on execution details.
- Move completed implementation notes into `STATUS.md`.
- Add migration notes whenever a stricter check changes example behavior.

### Compatibility

- Keep Python support aligned with `pyproject.toml` and CI.
- Avoid new runtime dependencies unless they remove substantial local code or
  provide a standard parser/schema engine.
- All new files should use ASCII unless existing files require otherwise.

### Release Management

- Update version only in release PRs.
- Keep `uv.lock` aligned with `pyproject.toml`.
- Use the existing publish workflow; do not manually create GitHub releases.

## Suggested Implementation Order

1. P0.1 Target Discovery
2. P0.2 CLI And Batch Runner
3. P0.3 Batch Fixtures And CI
4. P0.4 Regression Snapshots
5. P1.1 Schema Error Infrastructure
6. P1.2 Section Semantics Hardening
7. P1.3 Min Wall Thickness Range Mode
8. P1.4 Common-Error Negative Fixtures
9. P1.5 Weak-Check Review Gates
10. P2.1 Metadata Interface Schema
11. P2.2 Helper-Emitted Interfaces
12. P2.3 Assembly Fixture Expansion
13. P3.1 Doctor Command
14. P3.2 Suggest Checks
15. P4.1 Timing Instrumentation
16. P4.2 Section Cache
17. P5 tracks only after P0 and P1 are stable

This order intentionally front-loads reliability. It creates project-scale
feedback before tightening contracts, then uses the stronger contracts to make
assemblies and authoring guidance more trustworthy.

P1.3 (range mode) and P1.5 (review gates) were previously omitted from the
order but are part of P1 completion. P1.3 extends an existing check type and
P1.5 turns P1.2 warnings into blocking gates, so both follow P1.2 naturally.
