from __future__ import annotations

from typing import Any


def error_payload(err: Any = None, message: str | None = None, err_type: str = "Error") -> dict:
    if isinstance(err, dict):
        payload = dict(err)
        payload.setdefault("type", err_type)
        payload.setdefault("message", message or "operation failed")
        return payload
    if isinstance(err, str):
        return {"type": err_type, "message": err}
    if message:
        return {"type": err_type, "message": message}
    return {"type": err_type, "message": "operation failed"}


def stage_check(name: str, ok: bool, payload: dict | None = None) -> dict:
    item = {"name": name, "type": "stage", "ok": ok}
    if not ok:
        source = payload or {}
        item["error"] = error_payload(source.get("error"), source.get("message"), err_type=f"{name.title()}StageError")
    return item
