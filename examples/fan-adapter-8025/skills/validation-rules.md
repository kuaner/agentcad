# Validation Rules

Before completion:

1. `cad validate <name> --json` must return `ok: true`.
2. `outputs/geometry.json` must exist.
3. STEP/STL artifacts must exist unless the user requested a different format.
4. Preview artifacts must exist.
5. Design checks in `design.json` must pass or be explicitly marked out of scope.
