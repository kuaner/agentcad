from __future__ import annotations

import json
from pathlib import Path

from agentcad.workspace import (
    init_workspace,
    new_model,
    new_variant,
    outputs_dir,
    outputs_dir_for_variant,
    variant_dir,
    variant_params_path,
)
from agentcad.runner import build_model


def test_new_variant_creates_directory(tmp_path):
    init_workspace(tmp_path)
    new_model(tmp_path, "box")
    result = new_variant(tmp_path, "box", "small")
    assert result["ok"] is True
    v_dir = variant_dir(tmp_path, "box", "small")
    assert v_dir.is_dir()
    assert (v_dir / "params.json").exists()


def test_new_variant_copies_base_params(tmp_path):
    init_workspace(tmp_path)
    new_model(tmp_path, "box")
    base_params = tmp_path / "models" / "box" / "params.json"
    base_params.write_text(json.dumps({"width": 50, "height": 30}))
    result = new_variant(tmp_path, "box", "tiny")
    assert result["ok"] is True
    v_params = variant_params_path(tmp_path, "box", "tiny")
    data = json.loads(v_params.read_text())
    assert data["width"] == 50


def test_new_variant_with_custom_params(tmp_path):
    init_workspace(tmp_path)
    new_model(tmp_path, "box")
    result = new_variant(tmp_path, "box", "large", params={"width": 100})
    assert result["ok"] is True
    v_params = variant_params_path(tmp_path, "box", "large")
    data = json.loads(v_params.read_text())
    assert data["width"] == 100


def test_new_variant_duplicate_fails(tmp_path):
    init_workspace(tmp_path)
    new_model(tmp_path, "box")
    new_variant(tmp_path, "box", "v1")
    result = new_variant(tmp_path, "box", "v1")
    assert result["ok"] is False
    assert result["error"]["type"] == "VariantExists"


def test_outputs_dir_for_variant(tmp_path):
    base = outputs_dir(tmp_path, "box")
    variant = outputs_dir_for_variant(tmp_path, "box", "small")
    assert variant == base / "small"
    no_variant = outputs_dir_for_variant(tmp_path, "box", None)
    assert no_variant == base


def test_build_with_variant(tmp_path):
    init_workspace(tmp_path)
    new_model(tmp_path, "cube")
    model_root = tmp_path / "models" / "cube"
    model_root / "part.py".lstrip("/").rstrip("/")

    # Write a simple part.py that uses params
    (model_root / "part.py").write_text(
        "import json, build123d as b\n"
        "from pathlib import Path\n"
        "P = json.loads((Path(__file__).with_name('params.json')).read_text())\n"
        "s = float(P.get('size', 10))\n"
        "result = b.Box(s, s, s)\n"
    )
    (model_root / "params.json").write_text(json.dumps({"size": 10}))
    (model_root / "design.json").write_text(json.dumps({"intent": "cube", "features": [], "checks": []}))

    # Build base
    base_result = build_model(tmp_path, "cube")
    assert base_result["ok"] is True

    # Create and build variant with different size
    new_variant(tmp_path, "cube", "big", params={"size": 20})
    var_result = build_model(tmp_path, "cube", variant="big")
    assert var_result["ok"] is True

    # Verify variant output goes to separate directory
    var_out = outputs_dir_for_variant(tmp_path, "cube", "big")
    assert (var_out / "cube.stl").exists()
    assert var_out != outputs_dir(tmp_path, "cube")
