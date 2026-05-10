from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from .jsonio import read_json
from .workspace import normalize_model_name, outputs_dir


def archive_validation(out_dir: Path) -> Path | None:
    validation_path = out_dir / "validation.json"
    if not validation_path.exists():
        return None
    history_dir = out_dir / "validation-history"
    history_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    dest = history_dir / f"{ts}.json"
    shutil.copy2(validation_path, dest)
    return dest


def diff_validations(current: dict, previous: dict) -> dict:
    cur_checks = {c.get("name", ""): c for c in (current.get("checks") or [])}
    prev_checks = {c.get("name", ""): c for c in (previous.get("checks") or [])}
    cur_names = set(cur_checks)
    prev_names = set(prev_checks)

    fixed = []
    regressed = []
    stable_fail = []
    stable_pass = []

    for name in sorted(cur_names & prev_names):
        cc = cur_checks[name]
        pc = prev_checks[name]
        c_ok = cc.get("ok", False)
        p_ok = pc.get("ok", False)
        entry = {"name": name, "type": cc.get("type") or pc.get("type")}
        if c_ok and not p_ok:
            entry["previous_actual"] = pc.get("actual")
            entry["current_actual"] = cc.get("actual")
            fixed.append(entry)
        elif not c_ok and p_ok:
            entry["previous_actual"] = pc.get("actual")
            entry["current_actual"] = cc.get("actual")
            regressed.append(entry)
        elif not c_ok and not p_ok:
            entry["previous_actual"] = pc.get("actual")
            entry["current_actual"] = cc.get("actual")
            stable_fail.append(entry)
        else:
            stable_pass.append({"name": name, "type": cc.get("type")})

    new_checks = [{"name": n, "type": cur_checks[n].get("type")} for n in sorted(cur_names - prev_names)]
    removed = [{"name": n, "type": prev_checks[n].get("type")} for n in sorted(prev_names - cur_names)]

    return {
        "ok": True,
        "stage": "diff",
        "checks_fixed": fixed,
        "checks_regressed": regressed,
        "checks_stable_fail": stable_fail,
        "checks_stable_pass": stable_pass,
        "checks_new": new_checks,
        "checks_removed": removed,
        "geometry_drift": _geometry_drift(current, previous),
    }


def _geometry_drift(current: dict, previous: dict) -> dict:
    def _extract_geo(payload: dict) -> dict:
        g = payload.get("geometry") or {}
        if "bbox" not in g and "size" not in g:
            g = payload.get("auto_scan") or {}
        bbox = g.get("bbox") or {}
        size = bbox.get("size") or []
        mp = g.get("mass_properties") or {}
        mesh = g.get("mesh") or {}
        return {"bbox_size": size, "volume": mp.get("volume"), "triangles": mesh.get("triangles")}

    cur = _extract_geo(current)
    prev = _extract_geo(previous)
    drift: dict = {}
    if cur["bbox_size"] and prev["bbox_size"] and len(cur["bbox_size"]) == len(prev["bbox_size"]):
        drift["bbox_size_delta"] = [round(c - p, 4) for c, p in zip(cur["bbox_size"], prev["bbox_size"])]
    if cur["volume"] is not None and prev["volume"] is not None:
        drift["volume_delta"] = round(cur["volume"] - prev["volume"], 4)
    if cur["triangles"] is not None and prev["triangles"] is not None:
        drift["triangles_delta"] = cur["triangles"] - prev["triangles"]
    return drift


def diff_model(project: Path, name: str, *, last: bool = False) -> dict:
    safe = normalize_model_name(name)
    out_dir = outputs_dir(project, safe)
    current = read_json(out_dir / "validation.json", default=None)
    if current is None:
        return {"ok": False, "stage": "diff", "error": {"type": "NoValidation", "message": f"no validation.json for {safe}"}}

    history_dir = out_dir / "validation-history"
    if not history_dir.exists():
        return {"ok": False, "stage": "diff", "error": {"type": "NoHistory", "message": "no validation history; run validate at least twice"}}

    archives = sorted(history_dir.glob("*.json"), reverse=True)
    if not archives:
        return {"ok": False, "stage": "diff", "error": {"type": "NoHistory", "message": "no validation history; run validate at least twice"}}

    # archives[0] is the most recent previous run (last archived).
    # Default: compare current vs most recent previous run.
    # --last is a no-op alias kept for backward compatibility.
    target = archives[0]
    previous = read_json(target, default={})
    result = diff_validations(current, previous)
    result["model"] = safe
    result["compared_with"] = str(target)
    return result
