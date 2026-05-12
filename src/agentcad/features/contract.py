"""Contract builder for feature helpers.

Each helper returns a build123d shape and optionally registers feature +
check entries into a ``ContractBuilder``. The builder can then write or merge
the accumulated entries into ``design.json``.

Usage::

    from agentcad.features import ContractBuilder, plate, mounting_pattern

    b = ContractBuilder(intent="L-shaped bracket")
    plank = b.plate(100, 50, 5, fillet=2)
    pattern = b.mounting_pattern("M3_cap", spacing=25, count=4)
    b.write_to(project, "bracket")
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ContractBuilder:
    """Accumulates features, checks, and interfaces from helper calls."""

    def __init__(self, intent: str = "", units: str = "mm") -> None:
        self.intent = intent
        self.units = units
        self._features: list[dict[str, Any]] = []
        self._checks: list[dict[str, Any]] = []
        self._meta: dict[str, Any] = {}
        self._interfaces: dict[str, dict[str, Any]] = {}

    @property
    def features(self) -> list[dict[str, Any]]:
        return list(self._features)

    @property
    def checks(self) -> list[dict[str, Any]]:
        return list(self._checks)

    def add_feature(self, feature: dict[str, Any]) -> None:
        fid = feature.get("id", "")
        if any(f.get("id") == fid for f in self._features):
            raise ValueError(f"duplicate feature id: {fid!r}")
        self._features.append(feature)

    def add_check(self, check: dict[str, Any]) -> None:
        cid = check.get("id", "")
        if any(c.get("id") == cid for c in self._checks):
            raise ValueError(f"duplicate check id: {cid!r}")
        self._checks.append(check)
        # Auto-link: if check has feature_ref, add check ID to that feature's checks array
        ref = check.get("feature_ref", "")
        if ref:
            for feat in self._features:
                if feat.get("id") == ref:
                    feat.setdefault("checks", [])
                    if cid not in feat["checks"]:
                        feat["checks"].append(cid)
                    break

    def add(self, feature: dict[str, Any], checks: list[dict[str, Any]]) -> None:
        self.add_feature(feature)
        for check in checks:
            self.add_check(check)

    def add_interface(self, name: str, interface: dict[str, Any]) -> None:
        if name in self._interfaces:
            raise ValueError(f"duplicate interface name: {name!r}")
        self._interfaces[name] = interface

    @property
    def interfaces(self) -> dict[str, dict[str, Any]]:
        return dict(self._interfaces)

    def to_design(self) -> dict[str, Any]:
        """Build a design.json-compatible dict."""
        doc: dict[str, Any] = {
            "schema": "design-spec.v1",
            "units": self.units,
            "features": list(self._features),
            "checks": list(self._checks),
        }
        if self.intent:
            doc["intent"] = self.intent
        return doc

    def write_to(self, project: Path, name: str, *, merge: bool = True) -> dict[str, Any]:
        """Write (or merge into) ``models/<name>/design.json``."""
        from ..workspace import model_dir

        design_path = model_dir(project, name) / "design.json"
        if merge and design_path.exists():
            existing = json.loads(design_path.read_text(encoding="utf-8"))
        else:
            existing = {}

        new = self.to_design()
        new_feature_ids = {f.get("id") for f in new.get("features", [])}
        new_check_ids = {c.get("id") for c in new.get("checks", [])}

        for key in ("features", "checks"):
            existing_list = existing.get(key, [])
            new_list = new.get(key, [])
            existing_ids = {e.get("id") for e in existing_list}
            # Update or add entries from builder
            for entry in new_list:
                eid = entry.get("id", "")
                if eid in existing_ids:
                    # Merge: update existing entry with new keys (e.g. add checks array)
                    for existing_entry in existing_list:
                        if existing_entry.get("id") == eid:
                            for k, v in entry.items():
                                if k not in existing_entry:
                                    existing_entry[k] = v
                                elif k == "checks" and isinstance(v, list):
                                    # Merge check ID lists
                                    merged = list(existing_entry.get("checks", []))
                                    for cid in v:
                                        if cid not in merged:
                                            merged.append(cid)
                                    existing_entry["checks"] = merged
                            break
                else:
                    existing_list.append(entry)
            # Remove scaffold entries replaced by builder entries
            new_ids = new_feature_ids if key == "features" else new_check_ids
            if new_ids:
                existing[key] = [
                    e for e in existing_list
                    if e.get("id") in new_ids or not self._is_scaffold_id(e.get("id", ""), key)
                ]
            else:
                existing[key] = existing_list

        for key in ("schema", "units", "intent", "model"):
            if key in new and key not in existing:
                existing[key] = new[key]

        design_path.parent.mkdir(parents=True, exist_ok=True)
        design_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return existing

    @staticmethod
    def _is_scaffold_id(fid: str, key: str) -> bool:
        """Heuristic: scaffold templates use generic IDs like base_block, bbox_size, watertight."""
        scaffold_features = {"base_block"}
        scaffold_checks = {"bbox_size", "watertight"}
        if key == "features":
            return fid in scaffold_features
        return fid in scaffold_checks

    def to_metadata(self) -> dict[str, Any]:
        """Build a metadata.json-compatible dict."""
        doc: dict[str, Any] = {
            "schema": "agentcad.part.metadata.v1",
            "units": self.units,
        }
        if self._interfaces:
            doc["interfaces"] = dict(self._interfaces)
        return doc

    def write_metadata_to(self, project: Path, name: str, *, merge: bool = True) -> dict[str, Any]:
        """Write (or merge into) ``models/<name>/metadata.json``."""
        from ..workspace import model_dir

        metadata_path = model_dir(project, name) / "metadata.json"
        if merge and metadata_path.exists():
            existing = json.loads(metadata_path.read_text(encoding="utf-8"))
        else:
            existing = {}

        new = self.to_metadata()

        # Merge interfaces: add new ones, update existing ones with matching names.
        if "interfaces" in new:
            existing_interfaces = existing.get("interfaces", {})
            for iface_name, iface_data in new["interfaces"].items():
                existing_interfaces[iface_name] = iface_data
            existing["interfaces"] = existing_interfaces

        for key in ("schema", "units"):
            if key in new and key not in existing:
                existing[key] = new[key]

        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return existing
