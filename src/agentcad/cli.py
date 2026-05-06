from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .jsonio import print_payload
from .measure import measure_model
from .render import render_model
from .runner import build_model
from .validate import deliver_model, validate_model
from .workspace import find_project, init_workspace, new_model


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = dispatch(args)
    except Exception as exc:
        payload = {"ok": False, "stage": getattr(args, "command", "cli"), "error": {"type": type(exc).__name__, "message": str(exc)}}
        print_payload(payload, getattr(args, "json", False))
        return 1

    print_payload(payload, getattr(args, "json", False))
    return 0 if payload.get("ok", True) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cad", description="Agent-first CAD workflow runtime")
    parser.add_argument("--version", action="version", version=f"agentcad {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="create an AgentCAD workspace")
    init.add_argument("path", nargs="?", default=".")
    init.add_argument("--force", action="store_true")
    init.add_argument("--json", action="store_true")

    new = sub.add_parser("new", help="create a new model")
    add_project_arg(new)
    new.add_argument("model")
    new.add_argument("--force", action="store_true")
    new.add_argument("--json", action="store_true")

    build = sub.add_parser("build", help="build a model and export STEP/STL")
    add_project_arg(build)
    build.add_argument("model")
    build.add_argument("--json", action="store_true")

    measure = sub.add_parser("measure", help="measure generated STL geometry")
    add_project_arg(measure)
    measure.add_argument("model")
    measure.add_argument("--json", action="store_true")

    render = sub.add_parser("render", help="render an SVG preview from STL")
    add_project_arg(render)
    render.add_argument("model")
    render.add_argument("--view", choices=["iso", "front", "top", "side"], default="iso")
    render.add_argument("--json", action="store_true")

    validate = sub.add_parser("validate", help="build, measure, render, and validate a model")
    add_project_arg(validate)
    validate.add_argument("model")
    validate.add_argument("--view", choices=["iso", "front", "top", "side"], default="iso")
    validate.add_argument("--json", action="store_true")

    deliver = sub.add_parser("deliver", help="write a delivery manifest")
    add_project_arg(deliver)
    deliver.add_argument("model")
    deliver.add_argument("--no-validate", action="store_true")
    deliver.add_argument("--json", action="store_true")

    return parser


def add_project_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", default=".", help="project directory, defaults to current directory")


def dispatch(args: argparse.Namespace) -> dict:
    if args.command == "init":
        return init_workspace(Path(args.path), force=args.force)

    project = find_project(Path(args.project))
    if args.command == "new":
        return new_model(project, args.model, force=args.force)
    if args.command == "build":
        return build_model(project, args.model)
    if args.command == "measure":
        return measure_model(project, args.model)
    if args.command == "render":
        return render_model(project, args.model, view=args.view)
    if args.command == "validate":
        return validate_model(project, args.model, render_view=args.view)
    if args.command == "deliver":
        return deliver_model(project, args.model, run_validation=not args.no_validate)

    raise ValueError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
