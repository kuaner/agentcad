"""Tests for precheck.py and review.py commands."""
from __future__ import annotations

from pathlib import Path

import pytest

from agentcad.precheck import precheck_model
from agentcad.review import review_model
from agentcad.workspace import init_workspace, new_model


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    init_workspace(tmp_path)
    return tmp_path


@pytest.fixture
def model_with_clean_clearance(workspace: Path) -> tuple[Path, str]:
    """Scaffold a model whose design.json declares non-interfering shapes."""
    name = "good"
    new_model(workspace, name)
    design_path = workspace / "models" / name / "design.json"
    design_path.write_text(_design_json(
        name=name,
        clearances=[(["a", "b", -10, -10, 2.0, 4.0],
                     ["wall", -25, 25, 16, 20, 0, 30],
                     0.0)],
    ), encoding="utf-8")
    return workspace, name


@pytest.fixture
def model_with_interference(workspace: Path) -> tuple[Path, str]:
    """Mounting-bracket-style model whose hole interferes with a wall."""
    name = "buggy"
    new_model(workspace, name)
    design_path = workspace / "models" / name / "design.json"
    design_path.write_text(_design_json(
        name=name,
        clearances=[(["hole", "left", -15, 15, 2.25, 0, 4],
                     ["wall", -25, 25, 16, 20, 0, 30],
                     0.0)],
    ), encoding="utf-8")
    return workspace, name


def _design_json(name: str, clearances: list) -> str:
    """Compose a minimal design.json with given min_clearance check pairs.

    Each clearances entry: ([a_id, x_centre, y_centre, radius, z0, z1],
                            [b_id, x0, x1, y0, y1, z0, z1], min_mm)
    """
    import json

    checks = [{
        "id": f"{a[0]}_{a[1]}_clearance" if len(a) > 6 else f"{a[0]}_clearance",
        "type": "min_clearance",
        "feature_a": _cyl_or_box(a),
        "feature_b": _cyl_or_box(b),
        "min_mm": min_mm,
    } for (a, b, min_mm) in clearances]

    return json.dumps({
        "schema": "design-spec.v1",
        "model": name,
        "units": "mm",
        "intent": "Test fixture",
        "features": [
            {"id": "stuff", "intent": "test", "checks": [c["id"] for c in checks]}
        ],
        "checks": checks + [
            {"id": "stl_file", "type": "artifact_exists",
             "path": f"outputs/{name}.stl"},
        ],
    }, indent=2)


def _cyl_or_box(spec: list) -> dict:
    """Convert a compact spec into a shape descriptor."""
    if len(spec) == 7 and spec[0] == "hole":
        _, _, cx, cy, r, z0, z1 = spec
        return {"type": "cylinder", "axis": "z",
                "center": [float(cx), float(cy)], "radius": float(r),
                "z_range": [float(z0), float(z1)]}
    if len(spec) == 6 and spec[0] == "a":
        _, _, cx, cy, r, z = spec
        # Used only as plain cylinder; z is single endpoint, z_range = [0, z]
        return {"type": "cylinder", "axis": "z",
                "center": [float(cx), float(cy)], "radius": float(r),
                "z_range": [0.0, float(z)]}
    if len(spec) == 7 and spec[0] in ("wall", "box"):
        _, x0, x1, y0, y1, z0, z1 = spec
        return {"type": "box",
                "x_range": [float(x0), float(x1)],
                "y_range": [float(y0), float(y1)],
                "z_range": [float(z0), float(z1)]}
    raise ValueError(f"unsupported spec: {spec}")


# ── precheck ─────────────────────────────────────────────────────────────────

def test_precheck_passes_for_safe_design(model_with_clean_clearance):
    project, name = model_with_clean_clearance
    result = precheck_model(project, name)
    assert result["ok"] is True
    assert result["stage"] == "precheck"
    clearance_checks = [c for c in result["checks"] if c.get("type") == "min_clearance"]
    assert clearance_checks
    assert all(c["ok"] for c in clearance_checks)


def test_precheck_catches_interference(model_with_interference):
    project, name = model_with_interference
    result = precheck_model(project, name)
    assert result["ok"] is False
    interferences = [c for c in result["checks"]
                     if c.get("type") == "min_clearance" and not c["ok"]]
    assert len(interferences) == 1
    assert interferences[0]["actual_mm"] == pytest.approx(-1.25)
    assert "hint" in interferences[0]
    assert result["relations"]
    assert result["relations"][0]["interferes"] is True


def test_precheck_writes_artifact(model_with_clean_clearance):
    project, name = model_with_clean_clearance
    result = precheck_model(project, name)
    artifact = Path(result["artifacts"]["precheck"])
    assert artifact.exists()


def test_precheck_missing_design(workspace: Path):
    """Precheck fails gracefully when design.json is absent."""
    result = precheck_model(workspace, "nonexistent")
    assert result["ok"] is False
    failed = [c for c in result["checks"] if not c["ok"]]
    assert any("design.json not found" in str(c.get("error", "")) for c in failed)


def test_precheck_lists_deferred_checks(model_with_clean_clearance):
    project, name = model_with_clean_clearance
    result = precheck_model(project, name)
    deferred = result.get("deferred_to_validate") or []
    deferred_types = [d.get("type") for d in deferred]
    assert "artifact_exists" in deferred_types


def test_precheck_invalid_schema(workspace: Path):
    """Schema errors are reported before any clearance computation."""
    name = "bad_schema"
    new_model(workspace, name)
    design_path = workspace / "models" / name / "design.json"
    design_path.write_text(
        '{"schema":"v1","features":[{"id":"a"}],"checks":[{"type":"bbox_size"}]}',
        encoding="utf-8",
    )
    result = precheck_model(workspace, name)
    assert result["ok"] is False
    assert any(c.get("type") == "design_schema" for c in result["checks"])


# ── review ───────────────────────────────────────────────────────────────────

def test_review_blocks_delivery_on_interference(model_with_interference):
    project, name = model_with_interference
    result = review_model(project, name)
    assert result["ok"] is False
    assert result["ready_to_deliver"] is False
    interference_check = next(
        item for item in result["checklist"]
        if item["id"] == "no_pairwise_interference"
    )
    assert interference_check["ok"] is False


def test_review_relations_matrix_includes_all_pairs(model_with_interference):
    project, name = model_with_interference
    result = review_model(project, name)
    relations = result["relations"]
    assert relations
    interferences = [r for r in relations if r.get("interferes")]
    assert len(interferences) == 1


def test_review_must_view_includes_iso_when_present(model_with_clean_clearance):
    project, name = model_with_clean_clearance
    out_dir = project / "models" / name / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    iso = out_dir / "preview.iso.svg"
    iso.write_text("<svg/>", encoding="utf-8")
    result = review_model(project, name)
    labels = [v["label"] for v in result["must_view"]]
    assert "iso_preview" in labels


def test_review_must_view_requires_all_orthographic_previews(model_with_clean_clearance):
    project, name = model_with_clean_clearance
    result = review_model(project, name)
    labels = [v["label"] for v in result["must_view"]]
    assert labels[:5] == [
        "iso_preview",
        "front_preview",
        "top_preview",
        "side_preview",
        "back_preview",
    ]
    svg_check = next(item for item in result["checklist"] if item["id"] == "key_svgs_present")
    assert svg_check["ok"] is False


def test_review_writes_artifact(model_with_clean_clearance):
    project, name = model_with_clean_clearance
    result = review_model(project, name)
    artifact = Path(result["artifacts"]["review"])
    assert artifact.exists()


def test_review_missing_design(workspace: Path):
    result = review_model(workspace, "ghost")
    assert result["ok"] is False
    assert any(item["id"] == "design_present" and not item["ok"]
               for item in result["checklist"])


def test_review_blocks_missing_hole_accessibility(model_with_interference):
    project, name = model_with_interference
    result = review_model(project, name)
    access_check = next(
        item for item in result["checklist"]
        if item["id"] == "hole_accessibility_declared"
    )
    assert access_check["ok"] is False
    assert result["ok"] is False


def test_review_does_not_treat_every_cylinder_as_hole(model_with_clean_clearance):
    project, name = model_with_clean_clearance
    result = review_model(project, name)
    access_check = next(
        item for item in result["checklist"]
        if item["id"] == "hole_accessibility_declared"
    )
    assert access_check["ok"] is True
    assert access_check["evidence"]["declared_hole_count"] == 0
