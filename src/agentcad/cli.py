from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .inspect import inspect_model
from .jsonio import print_payload
from .measure import measure_model
from .precheck import precheck_model
from .probe import probe_model, probe_scan
from .render import VIEW_DIRS, render_model, render_models_multi
from .report import report_model
from .review import review_model
from .runner import build_model
from .section import AXIS_X, AXIS_Y, AXIS_Z, write_section_svg
from .stl import read_stl
from .validate import deliver_model, validate_model
from .workspace import find_project, init_workspace, new_model, outputs_dir, sync_workspace


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
    parser = argparse.ArgumentParser(prog="agentcad", description="Agent-first CAD workflow runtime")
    parser.add_argument("--version", action="version", version=f"agentcad {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    new = sub.add_parser("new", help="create a new model (auto-initializes workspace)")
    add_project_arg(new)
    new.add_argument("model")
    new.add_argument("--force", action="store_true")
    new.add_argument("--json", action="store_true")

    build = sub.add_parser("build", help="build a model and export STEP/STL")
    add_project_arg(build)
    build.add_argument("model")
    build.add_argument("--force", action="store_true", help="force rebuild even if source is unchanged")
    build.add_argument("--json", action="store_true")

    measure = sub.add_parser("measure", help="measure generated STL geometry")
    add_project_arg(measure)
    measure.add_argument("model")
    measure.add_argument("--json", action="store_true")

    render = sub.add_parser("render", help="render an SVG preview from STL")
    add_project_arg(render)
    render.add_argument("model")
    render.add_argument("--view", choices=["iso", "front", "top", "side", "back"], default="iso")
    render.add_argument(
        "--views",
        default=None,
        help="comma-separated list of views to render (e.g. iso,back,top); overrides --view",
    )
    render.add_argument("--section-z", dest="section_z", type=float, default=None,
                        help="render a Z cross-section SVG at this height (mm)")
    render.add_argument("--section-x", dest="section_x", type=float, default=None,
                        help="render an X cross-section SVG (YZ plane) at this position (mm)")
    render.add_argument("--section-y", dest="section_y", type=float, default=None,
                        help="render a Y cross-section SVG (XZ plane) at this position (mm)")
    render.add_argument("--json", action="store_true")

    validate = sub.add_parser("validate", help="build, measure, render, and validate a model")
    add_project_arg(validate)
    validate.add_argument("model")
    validate.add_argument("--view", choices=["iso", "front", "top", "side", "back"], default="iso")
    validate.add_argument(
        "--views",
        default=None,
        help="comma-separated list of views to render during validation (default: iso,back)",
    )
    validate.add_argument("--json", action="store_true")

    deliver = sub.add_parser("deliver", help="write a delivery manifest")
    add_project_arg(deliver)
    deliver.add_argument("model")
    deliver.add_argument("--no-validate", action="store_true")
    deliver.add_argument("--json", action="store_true")

    probe = sub.add_parser("probe", help="probe STL cross-section to get geometry values for design.json")
    add_project_arg(probe)
    probe.add_argument("model")
    probe.add_argument("--z", default=None, help="Z height(s) to probe, comma-separated")
    probe.add_argument("--x", default=None, help="X position(s) to probe (YZ plane), comma-separated")
    probe.add_argument("--y", default=None, help="Y position(s) to probe (XZ plane), comma-separated")
    probe.add_argument("--center", default="0,0", help="cx,cy for radial Z measurements (default: 0,0)")
    probe.add_argument("--cx", type=float, default=None, help="center X for radial Z measurements (alias to --center first value)")
    probe.add_argument("--cy", type=float, default=None, help="center Y for radial Z measurements (alias to --center second value)")
    probe.add_argument("--region", default=None, help="x0,y0,x1,y1 — solid/void region check at Z")
    probe.add_argument("--scan", action="store_true", help="scan the full axis profile instead of a single section")
    probe.add_argument("--axis", choices=["x", "y", "z"], default="z", help="axis to scan (default: z)")
    probe.add_argument("--samples", type=int, default=20, help="number of scan samples (default: 20)")
    probe.add_argument("--json", action="store_true")

    report = sub.add_parser("report", help="generate a human-readable Markdown validation report")
    add_project_arg(report)
    report.add_argument("model")
    report.add_argument("--json", action="store_true")

    inspect = sub.add_parser("inspect", help="three-axis scan + section SVGs + suggested probe commands")
    add_project_arg(inspect)
    inspect.add_argument("model")
    inspect.add_argument("--samples", type=int, default=20, help="scan samples per axis (default: 20)")
    inspect.add_argument("--json", action="store_true")

    precheck = sub.add_parser("precheck", help="solve design.json statically (before writing part.py)")
    add_project_arg(precheck)
    precheck.add_argument("model")
    precheck.add_argument("--json", action="store_true")

    review = sub.add_parser("review", help="pre-delivery checklist + pairwise relations matrix")
    add_project_arg(review)
    review.add_argument("model")
    review.add_argument("--json", action="store_true")

    sync = sub.add_parser("sync", help="update workspace scaffold files from templates")
    add_project_arg(sync)
    sync.add_argument("--dry-run", action="store_true", help="preview template updates without writing files")
    sync.add_argument("--only", default=None, help="sync only one template path prefix (e.g. references/)")
    sync.add_argument("--prune-deprecated", action="store_true", help="remove deprecated scaffold paths like skills/")
    sync.add_argument("--json", action="store_true")

    return parser


def add_project_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", default=".", help="project directory, defaults to current directory")


def _resolve_project(args: argparse.Namespace) -> Path:
    """Find existing project, or auto-init for 'new' command."""
    project = Path(getattr(args, "project", "."))
    try:
        return find_project(project)
    except FileNotFoundError:
        if args.command == "new":
            target = project.expanduser().resolve()
            init_workspace(target)
            return find_project(target)
        raise


def dispatch(args: argparse.Namespace) -> dict:
    if args.command == "sync":
        project = _resolve_project(args)
        return sync_workspace(
            project,
            dry_run=getattr(args, "dry_run", False),
            only=getattr(args, "only", None),
            prune_deprecated=getattr(args, "prune_deprecated", False),
        )

    project = _resolve_project(args)
    if args.command == "new":
        return new_model(project, args.model, force=args.force)
    if args.command == "build":
        return build_model(project, args.model, force=getattr(args, "force", False))
    if args.command == "measure":
        return measure_model(project, args.model)
    if args.command == "render":
        # Section SVG modes take priority over 3D view rendering.
        for attr, axis_int, axis_name in (
            ("section_z", AXIS_Z, "z"),
            ("section_x", AXIS_X, "x"),
            ("section_y", AXIS_Y, "y"),
        ):
            val = getattr(args, attr, None)
            if val is not None:
                stl_path = outputs_dir(project, args.model) / f"{args.model}.stl"
                if not stl_path.exists():
                    return {"ok": False, "stage": "render", "model": args.model,
                            "error": {"type": "STLMissing",
                                      "message": f"STL not found, run 'agentcad build {args.model}' first"}}
                triangles = read_stl(stl_path)
                out_dir = outputs_dir(project, args.model)
                svg_path = out_dir / f"section.{axis_name}{val:.2f}.svg"
                return write_section_svg(triangles, axis_int, val, svg_path)
        views_arg = getattr(args, "views", None)
        if views_arg:
            views = [v.strip() for v in views_arg.split(",") if v.strip() in VIEW_DIRS]
            return render_models_multi(project, args.model, views or [args.view])
        return render_model(project, args.model, view=args.view)
    if args.command == "validate":
        views_arg = getattr(args, "views", None)
        render_views = [v.strip() for v in views_arg.split(",") if v.strip() in VIEW_DIRS] if views_arg else None
        return validate_model(project, args.model, render_view=args.view, render_views=render_views)
    if args.command == "deliver":
        return deliver_model(project, args.model, run_validation=not args.no_validate)
    if args.command == "probe":
        if args.scan:
            return probe_scan(project, args.model, axis=args.axis, samples=args.samples)
        z_values = [float(v.strip()) for v in args.z.split(",") if v.strip()] if args.z else None
        x_values = [float(v.strip()) for v in args.x.split(",") if v.strip()] if args.x else None
        y_values = [float(v.strip()) for v in args.y.split(",") if v.strip()] if args.y else None
        if args.cx is not None or args.cy is not None:
            cx = float(args.cx if args.cx is not None else 0.0)
            cy = float(args.cy if args.cy is not None else 0.0)
        else:
            cx, cy = (float(v) for v in args.center.split(","))
        region = None
        if args.region:
            x0, y0, x1, y1 = (float(v) for v in args.region.split(","))
            region = ((x0, y0), (x1, y1))
        return probe_model(project, args.model,
                           z_values=z_values, x_values=x_values, y_values=y_values,
                           center=(cx, cy), region=region)
    if args.command == "report":
        return report_model(project, args.model)
    if args.command == "inspect":
        return inspect_model(project, args.model, scan_samples=args.samples)
    if args.command == "precheck":
        return precheck_model(project, args.model)
    if args.command == "review":
        return review_model(project, args.model)

    raise ValueError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
