from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .assembly import assembly_dir, init_assembly, list_assemblies, review_assembly, validate_assembly
from .diff import diff_model
from .inspect import inspect_model
from .jsonio import print_payload
from .measure import measure_model
from .precheck import precheck_model
from .probe import probe_model, probe_scan
from .preview import open_preview, serve_preview, write_assembly_preview, write_model_preview
from .render import VIEW_DIRS, render_model, render_models_multi
from .report import report_model
from .review import review_model
from .runner import build_model
from .section import AXIS_X, AXIS_Y, AXIS_Z, write_section_svg
from .stl import read_stl
from .batch import validate_all
from .snapshot import compare_snapshot, load_snapshot, snapshot_target, write_snapshot
from .validate import deliver_model, validate_model
from .workspace import find_project, init_workspace, model_dir, new_model, normalize_model_name, outputs_dir, outputs_dir_for_variant, sync_workspace


def _parse_model_target(target: str) -> tuple[str, str | None]:
    """Parse 'model' or 'model:variant' into (model, variant_or_None)."""
    if ":" not in target:
        return target, None
    model, variant = target.rsplit(":", 1)
    if not model or not variant:
        raise ValueError(f"invalid target '{target}': both model and variant name required around ':'")
    return model, variant


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
    parser.add_argument("--project", "-p", default=None, type=Path,
                        help="explicit project root directory (default: auto-detect from cwd)")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="initialize a workspace and create first model")
    init.add_argument("name", help="workspace name")
    init.add_argument("--model", default=None, help="create an initial model after workspace initialization")
    init.add_argument("--force", action="store_true")

    new = sub.add_parser("new", help="create a new model or variant (use model:variant)")
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

    preview = sub.add_parser("preview", help="generate an interactive local HTML preview for a model or assembly")
    preview.add_argument("target")
    preview.add_argument(
        "--kind",
        choices=["auto", "model", "assembly"],
        default="auto",
        help="preview target kind; auto detects models/<name> or assemblies/<name>",
    )
    preview.add_argument("--static", action="store_true", help="generate self-contained HTML with embedded assets (for offline use)")

    validate = sub.add_parser("validate", help="build, measure, render, and validate a model or all targets")
    validate.add_argument("model")
    validate.add_argument("--view", choices=["iso", "front", "top", "side", "back"], default="iso")
    validate.add_argument(
        "--views",
        default=None,
        help="comma-separated list of views to render during validation (default: iso,front,top,side,back)",
    )
    validate.add_argument("--models", action="store_true", help="when validating all, include models")
    validate.add_argument("--assemblies", action="store_true", help="when validating all, include assemblies")
    validate.add_argument("--include-variants", action="store_true", help="when validating all, include model variants")
    validate.add_argument("--include-slow", action="store_true", help="when validating all, include slow targets")
    validate.add_argument("--fail-fast", action="store_true", help="stop after first validation failure")
    validate.add_argument("--output", type=Path, default=None, help="path for batch validation report (default: .agentcad/validation/all.json)")

    deliver = sub.add_parser("deliver", help="write a delivery manifest")
    deliver.add_argument("model")
    deliver.add_argument("--no-validate", action="store_true")

    diff = sub.add_parser("diff", help="compare current vs previous validation run")
    diff.add_argument("model")
    diff.add_argument("--last", action="store_true", help="compare with last archived run")

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
    assembly_review = assembly_sub.add_parser("review", help="run assembly delivery gates")
    assembly_review.add_argument("assembly")

    snapshot = sub.add_parser("snapshot", help="regression snapshot management")
    snapshot_sub = snapshot.add_subparsers(dest="snapshot_command", required=True)
    snapshot_write = snapshot_sub.add_parser("write", help="write regression snapshots for validated targets")
    snapshot_write.add_argument("--target", default=None, help="specific model or assembly name (default: all)")
    snapshot_write.add_argument("--kind", choices=["model", "assembly", "auto"], default="auto")
    snapshot_write.add_argument("--all", action="store_true", help="write snapshots for all targets")
    snapshot_compare = snapshot_sub.add_parser("compare", help="compare current results against baseline snapshots")
    snapshot_compare.add_argument("--target", default=None, help="specific model or assembly name (default: all)")
    snapshot_compare.add_argument("--kind", choices=["model", "assembly", "auto"], default="auto")

    return parser


def _resolve_project(args: argparse.Namespace) -> Path:
    """Find existing project, or auto-init when creating a new model."""
    explicit = getattr(args, "project", None)
    if explicit is not None:
        resolved = Path(explicit).expanduser().resolve()
        if not (resolved / "cadproject.json").exists():
            raise FileNotFoundError(f"No cadproject.json found in {resolved}")
        return resolved
    project = Path(".")
    try:
        return find_project(project)
    except FileNotFoundError:
        if args.command == "new":
            # For `agentcad new <name>` in a plain directory, scaffold a
            # dedicated project folder named after the model by default.
            model_target = getattr(args, "model", "")
            model_name = model_target.rsplit(":", 1)[0] if ":" in model_target else model_target
            if project == Path("."):
                target = (Path.cwd() / model_name).expanduser().resolve()
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
        if args.assembly_command == "review":
            return review_assembly(project, args.assembly)
    if args.command == "new":
        model_name, variant_name = _parse_model_target(args.model)
        if variant_name:
            from .workspace import new_variant
            return new_variant(project, model_name, variant_name)
        return new_model(project, model_name, force=args.force)
    if args.command == "build":
        model_name, variant_name = _parse_model_target(args.model)
        return build_model(project, model_name, force=getattr(args, "force", False), variant=variant_name)
    if args.command == "measure":
        model_name, variant_name = _parse_model_target(args.model)
        return measure_model(project, model_name, variant=variant_name)
    if args.command == "render":
        model_name, variant_name = _parse_model_target(args.model)
        out_dir = outputs_dir_for_variant(project, model_name, variant_name)
        # Section SVG modes take priority over 3D view rendering.
        for attr, axis_int, axis_name in (
            ("section_z", AXIS_Z, "z"),
            ("section_x", AXIS_X, "x"),
            ("section_y", AXIS_Y, "y"),
        ):
            val = getattr(args, attr, None)
            if val is not None:
                stl_path = out_dir / f"{model_name}.stl"
                if not stl_path.exists():
                    return {"ok": False, "stage": "render", "model": model_name,
                            "error": {"type": "STLMissing",
                                      "message": f"STL not found, run 'agentcad build {model_name}' first"}}
                triangles = read_stl(stl_path)
                svg_path = out_dir / f"section.{axis_name}{val:.2f}.svg"
                return write_section_svg(triangles, axis_int, val, svg_path)
        views_arg = getattr(args, "views", None)
        if views_arg:
            views = [v.strip() for v in views_arg.split(",") if v.strip() in VIEW_DIRS]
            return render_models_multi(project, model_name, views or [args.view], variant=variant_name)
        return render_model(project, model_name, view=args.view, variant=variant_name)
    if args.command == "preview":
        target, variant_name = _parse_model_target(args.target)
        return _preview_target(
            project, target,
            kind=getattr(args, "kind", "auto"),
            variant=variant_name,
            static=getattr(args, "static", False),
        )
    if args.command == "validate":
        if args.model == "all":
            include_models = getattr(args, "models", False)
            include_assemblies = getattr(args, "assemblies", False)
            # If neither --models nor --assemblies is specified, include both.
            if not include_models and not include_assemblies:
                include_models = True
                include_assemblies = True
            return validate_all(
                project,
                include_models=include_models,
                include_assemblies=include_assemblies,
                include_variants=getattr(args, "include_variants", False),
                include_slow=getattr(args, "include_slow", False),
                fail_fast=getattr(args, "fail_fast", False),
                output=getattr(args, "output", None),
            )
        model_name, variant_name = _parse_model_target(args.model)
        views_arg = getattr(args, "views", None)
        render_views = [v.strip() for v in views_arg.split(",") if v.strip() in VIEW_DIRS] if views_arg else None
        return validate_model(project, model_name, render_view=args.view, render_views=render_views, variant=variant_name)
    if args.command == "deliver":
        model_name, variant_name = _parse_model_target(args.model)
        return deliver_model(project, model_name, run_validation=not args.no_validate, variant=variant_name)
    if args.command == "diff":
        model_name, _ = _parse_model_target(args.model)
        return diff_model(project, model_name, last=getattr(args, "last", False))
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

    if args.command == "snapshot":
        return _dispatch_snapshot(project, args)

    raise ValueError(f"unknown command: {args.command}")


def _preview_target(project: Path, target: str, *, kind: str = "auto", variant: str | None = None, static: bool = False) -> dict:
    safe = normalize_model_name(target)
    has_model = model_dir(project, safe).exists()
    has_assembly = (assembly_dir(project, safe) / "assembly.json").exists()

    result: dict | None = None

    if kind == "model":
        if not has_model:
            return _preview_not_found(safe, kind="model")
        result = write_model_preview(project, safe, variant=variant, static=static)
    elif kind == "assembly":
        if not has_assembly:
            return _preview_not_found(safe, kind="assembly")
        result = write_assembly_preview(project, safe, static=static)
    elif has_model and has_assembly:
        return {
            "ok": False,
            "stage": "preview",
            "target": safe,
            "error": {
                "type": "AmbiguousPreviewTarget",
                "message": f"both model and assembly exist for {safe}; pass --kind model or --kind assembly",
            },
        }
    elif has_model:
        result = write_model_preview(project, safe, variant=variant, static=static)
    elif has_assembly:
        result = write_assembly_preview(project, safe, static=static)
    else:
        return {
            "ok": False,
            "stage": "preview",
            "target": safe,
            "error": {
                "type": "PreviewTargetNotFound",
                "message": f"no model or assembly found for {safe}",
            },
        }

    if result and result.get("ok") and result.get("artifacts", {}).get("preview_page"):
        preview_path = Path(result["artifacts"]["preview_page"])
        if static:
            open_preview(preview_path)
        else:
            serve_preview(preview_path)

    return result


def _dispatch_snapshot(project: Path, args: argparse.Namespace) -> dict:
    from .batch import discover_validation_targets
    if args.snapshot_command == "write":
        targets = discover_validation_targets(project)
        target_name = getattr(args, "target", None)
        if target_name:
            targets = [t for t in targets if t.name == target_name]
        if not targets:
            return {"ok": False, "stage": "snapshot_write", "error": {"type": "NoTargets", "message": "no validation targets found"}}
        paths = []
        for t in targets:
            # Read the validation payload for this target.
            kind = t.kind
            name = t.name
            variant = t.variant
            if kind == "model":
                from .workspace import outputs_dir_for_variant
                v_path = outputs_dir_for_variant(project, name, variant) / "validation.json"
            else:
                from .assembly import assembly_outputs_dir
                v_path = assembly_outputs_dir(project, name) / "assembly_validation.json"
            from .jsonio import read_json
            payload = read_json(v_path, default=None)
            if payload is None:
                continue
            target_dict = {"kind": t.kind, "name": t.name, "variant": t.variant}
            path = write_snapshot(project, target_dict, payload)
            paths.append(str(path))
        return {
            "ok": True,
            "stage": "snapshot_write",
            "project": str(project),
            "snapshots_written": len(paths),
            "paths": paths,
        }

    if args.snapshot_command == "compare":
        targets = discover_validation_targets(project)
        target_name = getattr(args, "target", None)
        if target_name:
            targets = [t for t in targets if t.name == target_name]
        if not targets:
            return {"ok": False, "stage": "snapshot_compare", "error": {"type": "NoTargets", "message": "no validation targets found"}}
        comparisons = []
        for t in targets:
            kind = t.kind
            name = t.name
            variant = t.variant
            if kind == "model":
                from .workspace import outputs_dir_for_variant
                v_path = outputs_dir_for_variant(project, name, variant) / "validation.json"
            else:
                from .assembly import assembly_outputs_dir
                v_path = assembly_outputs_dir(project, name) / "assembly_validation.json"
            from .jsonio import read_json
            payload = read_json(v_path, default=None)
            if payload is None:
                continue
            target_dict = {"kind": t.kind, "name": t.name, "variant": t.variant}
            current = snapshot_target(project, target_dict, payload)
            baseline = load_snapshot(project, target_dict)
            if baseline is None:
                comparisons.append({"target": target_dict, "ok": False, "error": "no baseline snapshot"})
                continue
            comparisons.append(compare_snapshot(current, baseline))
        ok = all(c.get("ok", True) for c in comparisons)
        return {
            "ok": ok,
            "stage": "snapshot_compare",
            "project": str(project),
            "comparisons": comparisons,
        }

    raise ValueError(f"unknown snapshot command: {args.snapshot_command}")


def _preview_not_found(target: str, *, kind: str) -> dict:
    return {
        "ok": False,
        "stage": "preview",
        "target": target,
        "kind": kind,
        "error": {
            "type": "PreviewTargetNotFound",
            "message": f"no {kind} found for {target}",
        },
    }


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
