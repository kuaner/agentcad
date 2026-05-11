from __future__ import annotations

import json

import pytest

from agentcad.features import ContractBuilder


class TestContractBuilder:
    def test_empty_builder(self):
        b = ContractBuilder(intent="test part")
        doc = b.to_design()
        assert doc["intent"] == "test part"
        assert doc["features"] == []
        assert doc["checks"] == []

    def test_add_feature_and_checks(self):
        b = ContractBuilder()
        b.add(
            feature={"id": "plate", "description": "a plate"},
            checks=[{"id": "plate_bbox", "type": "bbox_size", "expected": [10, 20, 3]}],
        )
        assert len(b.features) == 1
        assert len(b.checks) == 1
        assert b.features[0]["id"] == "plate"

    def test_duplicate_feature_id_raises(self):
        b = ContractBuilder()
        b.add_feature({"id": "plate", "description": "first"})
        with pytest.raises(ValueError, match="duplicate feature id"):
            b.add_feature({"id": "plate", "description": "second"})

    def test_duplicate_check_id_raises(self):
        b = ContractBuilder()
        b.add_check({"id": "bbox", "type": "bbox_size"})
        with pytest.raises(ValueError, match="duplicate check id"):
            b.add_check({"id": "bbox", "type": "watertight"})

    def test_write_to_creates_design_json(self, tmp_path):
        from agentcad.workspace import init_workspace, new_model

        init_workspace(tmp_path / "proj")
        new_model(tmp_path / "proj", "part")

        b = ContractBuilder(intent="test")
        b.add(
            feature={"id": "test_plate", "description": "plate"},
            checks=[{"id": "test_plate_bbox", "type": "bbox_size", "expected": [10, 10, 3]}],
        )
        result = b.write_to(tmp_path / "proj", "part")
        feat_ids = [f["id"] for f in result["features"]]
        assert "test_plate" in feat_ids

        design_path = tmp_path / "proj" / "models" / "part" / "design.json"
        assert design_path.exists()
        loaded = json.loads(design_path.read_text())
        loaded_ids = [f["id"] for f in loaded["features"]]
        assert "test_plate" in loaded_ids

    def test_write_to_merges_with_existing(self, tmp_path):
        from agentcad.workspace import init_workspace, new_model

        proj = tmp_path / "proj"
        init_workspace(proj)
        new_model(proj, "part")
        design_path = proj / "models" / "part" / "design.json"
        design_path.write_text(json.dumps({
            "schema": "design-spec.v1",
            "features": [{"id": "existing_feat", "description": "old"}],
            "checks": [{"id": "existing_check", "type": "watertight"}],
        }))

        b = ContractBuilder()
        b.add(
            feature={"id": "new_feat", "description": "new"},
            checks=[{"id": "new_check", "type": "bbox_size", "expected": [1, 1, 1]}],
        )
        result = b.write_to(proj, "part")
        feat_ids = [f["id"] for f in result["features"]]
        check_ids = [c["id"] for c in result["checks"]]
        assert "existing_feat" in feat_ids
        assert "new_feat" in feat_ids
        assert "existing_check" in check_ids
        assert "new_check" in check_ids
