# CAD Workflow

For every model:

```text
edit design/params/source -> cad validate <name> --json -> fix -> repeat -> cad deliver <name> --json
```

Use `cad validate` as the main self-check command. It runs build, measurement,
preview rendering, and design checks.
