"""Tests for JSON read/write helpers."""
from __future__ import annotations

from agentcad.jsonio import print_payload, read_json, write_json


def test_write_and_read_json(tmp_path):
    payload = {"key": "value", "num": 42}
    path = tmp_path / "test.json"
    write_json(path, payload)
    result = read_json(path)
    assert result == payload


def test_read_json_missing_returns_default(tmp_path):
    result = read_json(tmp_path / "nonexistent.json", default={"fallback": True})
    assert result == {"fallback": True}


def test_write_json_creates_parent_dirs(tmp_path):
    path = tmp_path / "deep" / "nested" / "file.json"
    write_json(path, {"ok": True})
    assert path.exists()


def test_read_json_missing_no_default(tmp_path):
    result = read_json(tmp_path / "nonexistent.json")
    assert result is None
