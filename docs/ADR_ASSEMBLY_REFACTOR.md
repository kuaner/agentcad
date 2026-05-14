# ADR: Assembly Subsystem Refactor

Date: 2026-05-14

## Context

`src/agentcad/assembly.py` grew to more than 2500 lines and mixed orchestration,
component loading, metadata reference resolution, mate checks, mesh collision
algorithms, assembly checks, previews, STL export, MJCF export, and review
payload generation.

This is now a subsystem, not a single module. Future assembly work should not
continue adding unrelated behavior to one file.

## Decision

Turn `agentcad.assembly` into a package while preserving the existing public
import path:

```python
from agentcad.assembly import validate_assembly
```

The public API remains:

- `assemblies_dir`
- `assembly_dir`
- `assembly_outputs_dir`
- `init_assembly`
- `list_assemblies`
- `measure_assembly`
- `validate_assembly`
- `review_assembly`

The package is split by responsibility:

```text
agentcad/assembly/
  __init__.py      public compatibility exports
  core.py          init/list/measure/validate orchestration and check rules
  types.py         schemas, errors, transform data model
  paths.py         workspace path helpers
  components.py    component loading, builds, metadata, public records
  transform.py     transform parsing and point/vector/triangle transforms
  references.py    metadata reference resolution and descriptor transforms
  metadata_checks.py metadata schema and interface geometry consistency checks
  mates.py         coaxial/coincident/axis/engagement evaluation
  mesh.py          pairwise mesh evidence and triangle geometry
  artifacts.py     SVG preview, STL export, MJCF export, consistency checks
  review.py        review_assembly gates
```

Intentionally left in `core.py` for now:

- `checks.py`: assembly validation checks and interface contract checks

The remaining check code is still cohesive enough to keep together until the
check taxonomy changes again. The next extraction should split it only when
there is a concrete need, for example separating feature evidence matrix gates
from pairwise assembly safety gates.

## Constraints

- Keep CLI behavior and JSON payload schemas stable.
- Keep `agentcad.assembly` import-compatible for downstream code.
- Move code mechanically first; change behavior only in separate, tested steps.
- Pure mesh algorithms must not depend on workspace, JSON I/O, runner, or CLI.
- Every extraction phase must pass assembly, CLI, batch, and snapshot tests.

## Acceptance

- `uv run pytest tests/test_assembly.py tests/test_batch.py tests/test_snapshot.py tests/test_cli.py -q`
- Final phase: `uv run pytest -q`
