from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .assembly import init_assembly, list_assemblies, review_assembly, validate_assembly
from .inspect import inspect_model
from .jsonio import print_payload
from .measure import measure_model
from .precheck import precheck_model
from .probe import probe_model, probe_scan
from .preview import write_assembly_preview, write_model_preview
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
        print_payload(payload)
        return 1

    print_payload(payload)
    return 0 if payload.get("ok", True) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentcad", description="Agent-first CAD workflow runtime")
    parser.add_argument("--version", action="version", version=f"agentcad {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="initialize a workspace and create first model")
    init.add_argument("name", help="workspace name")
    init.add_argument("--model", default=None, help="create an initial model after workspace initialization")
    init.add_argument("--force", action="store_true")

    new = sub.add_parser("new", help="create a new model (auto-initializes workspace)")
    new.add_argument("model")
    new.add_argument("--force", action="store_true")

    build = sub.add_parser("build", help="build a model and export STEP/STL")
    build.add_argument("model")
    build.add_argument("--force", action="store_true", help="force rebuild even if source is unchanged")

    measure = sub.add_parser("measure", help="measure generated STL geometry")
    measure.add_argument("model")

    render = sub.add_parser("render", help="render an SVG preview from STL")
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

    preview = sub.add_parser("preview", help="generate an interactive local HTML preview")
    preview.add_argument("model")

    validate = sub.add_parser("validate", help="build, measure, render, and validate a model")
    validate.add_argument("model")
    validate.add_argument("--view", choices=["iso", "front", "top", "side", "back"], default="iso")
    validate.add_argument(
        "--views",
        default=None,
        help="comma-separated list of views to render during validation (default: iso,back)",
    )

    deliver = sub.add_parser("deliver", help="write a delivery manifest")
    deliver.add_argument("model")
    deliver.add_argument("--no-validate", action="store_true")

    probe = sub.add_parser("probe", help="probe STL cross-section to get geometry values for design.json")
    probe.add_argument("model")
    probe.add_argument("--z", default=None, help="Z height(s) to probe, comma-separated")
    probe.add_argument("--x", default=None, help="X position(s) to probe (YZ plane), comma-separated")
    probe.add_argument("--y", default=None, help="Y position(s) to probe (XZ plane), comma-separated")
    probe.add_argument("--center", default="0,0", help="cx,cy for radial Z measurements (default: 0,0)")
    probe.add_argument("--cx", type=float, default=None, help="center X for radial Z measurements (alias to --center first value)")
    probe.add_argument("--cy", type=float, default=None, help="center Y for radial Z measurements (alias to --center second value)")
    probe.add_argument("--region", default=None, help="x0,y0,x1,y1 — solid/void region check at Z")
    probe.add_argument("--section-region", default=None, help="u0,v0,u1,v1 in the active section plane")
    probe.add_argument("--line-u", type=float, default=None, help="measure contour intersections at fixed section U coordinate")
    probe.add_argument("--line-v", type=float, default=None, help="measure contour intersections at fixed section V coordinate")
    probe.add_argument("--point", default=None, help="u,v in the active section plane for nearest-contour distance")
    probe.add_argument("--scan", action="store_true", help="scan the full axis profile instead of a single section")
    probe.add_argument("--axis", choices=["x", "y", "z"], default="z", help="axis to scan (default: z)")
    probe.add_argument("--samples", type=int, default=20, help="number of scan samples (default: 20)")

    report = sub.add_parser("report", help="generate a human-readable Markdown validation report")
    report.add_argument("model")

    inspect = sub.add_parser("inspect", help="three-axis scan + section SVGs + suggested probe commands")
    inspect.add_argument("model")
    inspect.add_argument("--samples", type=int, default=20, help="scan samples per axis (default: 20)")

    precheck = sub.add_parser("precheck", help="solve design.json statically (before writing part.py)")
    precheck.add_argument("model")

    review = sub.add_parser("review", help="pre-delivery checklist + pairwise relations matrix")
    review.add_argument("model")

    sync = sub.add_parser("sync", help="update workspace scaffold files from templates")
    sync.add_argument("--dry-run", action="store_true", help="preview template updates without writing files")
    sync.add_argument("--only", default=None, help="sync only one template path prefix (e.g. references/)")
    sync.add_argument("--prune-deprecated", action="store_true", help="remove deprecated scaffold paths like skills/")

    assembly = sub.add_parser("assembly", help="create, validate, and review multi-model assemblies")
    assembly_sub = assembly.add_subparsers(dest="assembly_command", required=True)
    assembly_init = assembly_sub.add_parser("init", help="create an assembly contract")
    assembly_init.add_argument("assembly")
    assembly_init.add_argument("--force", action="store_true")
    assembly_sub.add_parser("list", help="list assemblies in this workspace")
    assembly_validate = assembly_sub.add_parser("validate", help="measure, check, render, and export MJCF for an assembly")
    assembly_validate.add_argument("assembly")
    assembly_preview = assembly_sub.add_parser("preview", help="generate an interactive local HTML assembly preview")
    assembly_preview.add_argument("assembly")
    assembly_review = assembly_sub.add_parser("review", help="run assembly delivery gates")
    assembly_review.add_argument("assembly")

    return parser


def _resolve_project(args: argparse.Namespace) -> Path:
    """Find existing project, or auto-init when creating a new model."""
    project = Path(".")
    try:
        return find_project(project)
    except FileNotFoundError:
        if args.command == "new":
            # For `agentcad new <name>` in a plain directory, scaffold a
            # dedicated project folder named after the model by default.
            if project == Path("."):
                target = (Path.cwd() / args.model).expanduser().resolve()
            else:
                target = project.expanduser().resolve()
            init_workspace(target)
            return find_project(target)
        raise


def dispatch(args: argparse.Namespace) -> dict:
    if args.command == "init":
        workspace_name = str(getattr(args, "name"))
        model_name = str(getattr(args, "model", "") or workspace_name)
        target = (Path.cwd() / workspace_name).resolve()

        init_payload = init_workspace(target, force=getattr(args, "force", False))
        model_payload = new_model(target, model_name, force=getattr(args, "force", False))
        return {
            "ok": bool(init_payload.get("ok")) and bool(model_payload.get("ok")),
            "stage": "init",
            "project": str(target),
            "workspace": init_payload,
            "model": model_payload,
        }

    if args.command == "sync":
        project = _resolve_project(args)
        return sync_workspace(
            project,
            dry_run=getattr(args, "dry_run", False),
            only=getattr(args, "only", None),
            prune_deprecated=getattr(args, "prune_deprecated", False),
        )

    project = _resolve_project(args)
    if args.command == "assembly":
        if args.assembly_command == "init":
            return init_assembly(project, args.assembly, force=getattr(args, "force", False))
        if args.assembly_command == "list":
            return list_assemblies(project)
        if args.assembly_command == "validate":
            return validate_assembly(project, args.assembly)
        if args.assembly_command == "preview":
            return write_assembly_preview(project, args.assembly)
        if args.assembly_command == "review":
            return review_assembly(project, args.assembly)
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
    if args.command == "preview":
        return write_model_preview(project, args.model)
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
        center_cx, center_cy = (float(v) for v in args.center.split(","))
        if args.cx is not None or args.cy is not None:
            # Merge explicit axis overrides with --center defaults.
            cx = float(args.cx if args.cx is not None else center_cx)
            cy = float(args.cy if args.cy is not None else center_cy)
        else:
            cx, cy = center_cx, center_cy
        region = None
        if args.region:
            x0, y0, x1, y1 = (float(v) for v in args.region.split(","))
            region = ((x0, y0), (x1, y1))
        section_region = None
        if args.section_region:
            u0, v0, u1, v1 = (float(v) for v in args.section_region.split(","))
            section_region = ((u0, v0), (u1, v1))
        point = None
        if args.point:
            u, v = (float(v) for v in args.point.split(","))
            point = (u, v)
        return probe_model(project, args.model,
                           z_values=z_values, x_values=x_values, y_values=y_values,
                           center=(cx, cy), region=region,
                           section_region=section_region,
                           line_u=args.line_u,
                           line_v=args.line_v,
                           point=point)
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
