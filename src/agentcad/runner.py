from __future__ import annotations

import contextlib
import hashlib
import io
import os
import runpy
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .jsonio import read_json, write_json
from .workspace import model_dir, outputs_dir, outputs_dir_for_variant, variant_params_path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_hash(root: Path, variant_params: Path | None = None) -> str:
    """Compute a short hash over part.py and params.json to detect source changes."""
    h = hashlib.sha256()
    for fname in ("part.py", "params.json"):
        p = root / fname
        if p.exists():
            h.update(fname.encode())
            h.update(p.read_bytes())
    if variant_params is not None and variant_params.exists():
        h.update(b"variant_params")
        h.update(variant_params.read_bytes())
    return h.hexdigest()[:16]


def build_model(project: Path, name: str, force: bool = False, variant: str | None = None) -> dict:
    root = model_dir(project, name)
    source = root / "part.py"
    out_dir = outputs_dir_for_variant(project, name, variant)
    out_dir.mkdir(parents=True, exist_ok=True)
    build_report_path = out_dir / "build.json"

    if not source.exists():
        payload = _failure(name, "build", "SourceMissing", f"missing source file: {source}", source)
        write_json(build_report_path, payload)
        return payload

    v_params = variant_params_path(project, name, variant) if variant else None
    source_hash = _source_hash(root, v_params)

    # Return cached build when source is unchanged and artifacts exist.
    if not force and build_report_path.exists():
        stl_path = out_dir / f"{name}.stl"
        step_path = out_dir / f"{name}.step"
        cached = read_json(build_report_path, default={}) or {}
        if (
            cached.get("ok")
            and cached.get("sourceHash") == source_hash
            and stl_path.exists()
            and step_path.exists()
        ):
            return {**cached, "skipped": True, "message": "source unchanged, using cached build"}

    stdout = io.StringIO()
    stderr = io.StringIO()
    started_at = utc_now()
    old_path = list(sys.path)
    if variant:
        os.environ["AGENTCAD_VARIANT"] = variant
        if v_params and v_params.exists():
            os.environ["AGENTCAD_VARIANT_PARAMS"] = str(v_params)
    try:
        sys.path.insert(0, str(root))
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            namespace = runpy.run_path(str(source), run_name=f"__agentcad_model_{name}__")
    except Exception as exc:
        tb = traceback.format_exc()
        line = _extract_error_line(tb, str(source))
        payload = _failure(name, "build", type(exc).__name__, str(exc), source)
        if line is not None:
            payload["error"]["line"] = line
        payload["stdout"] = stdout.getvalue()
        payload["stderr"] = stderr.getvalue() + tb
        payload["startedAt"] = started_at
        payload["endedAt"] = utc_now()
        write_json(build_report_path, payload)
        return payload
    finally:
        sys.path[:] = old_path
        os.environ.pop("AGENTCAD_VARIANT", None)
        os.environ.pop("AGENTCAD_VARIANT_PARAMS", None)

    result = namespace.get("result")
    if result is None:
        payload = _failure(name, "build", "MissingResult", "part.py must define global variable result", source)
        payload["stdout"] = stdout.getvalue()
        payload["stderr"] = stderr.getvalue()
        payload["startedAt"] = started_at
        payload["endedAt"] = utc_now()
        write_json(build_report_path, payload)
        return payload

    step_path = out_dir / f"{name}.step"
    stl_path = out_dir / f"{name}.stl"
    metadata_path = root / "metadata.json"
    try:
        from build123d import export_step, export_stl  # type: ignore

        export_step(result, str(step_path))
        export_stl(result, str(stl_path))
    except Exception as exc:
        tb = traceback.format_exc()
        payload = _failure(name, "export", type(exc).__name__, str(exc), source)
        payload["stdout"] = stdout.getvalue()
        payload["stderr"] = stderr.getvalue() + tb
        payload["startedAt"] = started_at
        payload["endedAt"] = utc_now()
        write_json(build_report_path, payload)
        return payload

    metadata = namespace.get("metadata")
    if metadata is not None:
        try:
            write_json(metadata_path, _json_safe(metadata))
        except Exception as exc:
            payload = _failure(name, "metadata", type(exc).__name__, str(exc), source)
            payload["stdout"] = stdout.getvalue()
            payload["stderr"] = stderr.getvalue()
            payload["startedAt"] = started_at
            payload["endedAt"] = utc_now()
            write_json(build_report_path, payload)
            return payload

    payload = {
        "ok": True,
        "stage": "build",
        "model": name,
        "sourceHash": source_hash,
        "startedAt": started_at,
        "endedAt": utc_now(),
        "artifacts": {
            "step": str(step_path),
            "stl": str(stl_path),
            "build": str(build_report_path),
            "metadata": str(metadata_path) if metadata is not None else None,
        },
        "stdout": stdout.getvalue(),
        "stderr": stderr.getvalue(),
        "message": "model built",
    }
    write_json(build_report_path, payload)
    return payload


def _extract_error_line(tb_text: str, source_path: str) -> int | None:
    """Extract line number from traceback for the model source file."""
    for line in tb_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("File") and source_path in stripped:
            parts = stripped.split(",")
            for part in parts:
                part = part.strip()
                if part.startswith("line "):
                    try:
                        return int(part.split()[1])
                    except (IndexError, ValueError):
                        pass
    return None


def _failure(model: str, stage: str, error_type: str, message: str, source: Path) -> dict:
    return {
        "ok": False,
        "stage": stage,
        "model": model,
        "error": {
            "type": error_type,
            "message": message,
            "file": str(source),
        },
    }


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if hasattr(value, "to_tuple"):
        return _json_safe(value.to_tuple())
    raise TypeError(f"metadata contains non-JSON value of type {type(value).__name__}")
