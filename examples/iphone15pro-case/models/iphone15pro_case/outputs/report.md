# Validation Report — `iphone15pro_case`

**Status**: ✅ PASSED  
**Validated at**: 2026-05-07T03:09:23.674130+00:00

## Pipeline Stages

| Stage | Status |
|-------|--------|
| build | ✅ |
| measure | ✅ |
| render | ✅ |

## Design Checks

| Check | Type | Status | Details |
|-------|------|--------|---------|
| overall_bbox | bbox_size | ✅ | expected [75.2, 151.2, 11.25] ±0.5, actual [75.19999694824219, 151.1999969482422, 11.25] |
| watertight | watertight | ✅ | expected True, actual True |
| mesh_detail | min_triangles | ✅ | expected ≥300, actual 1788 |
| volume_check | volume_range | ✅ | 21580.2mm³ in [12000, 32000] |
| step_artifact | artifact_exists | ✅ | — |
| stl_artifact | artifact_exists | ✅ | — |
| camera_hole_section | inner_diameter_at_z | ✅ | z=0.75, ⌀inner expected 39.5±5.0mm, actual 44.49mm |
| back_panel_ring | section_bbox_at_z | ✅ | z=0.75, expected solid, actual solid (102 pts) |
| usbc_slot_void | section_bbox_at_z | ✅ | z=5.8, expected solid, actual solid (12 pts) |

## Feature Coverage

| Feature | Status | Matched Checks |
|---------|--------|----------------|
| outer_shell | ✅ | overall_bbox, watertight, mesh_detail |
| inner_cavity | ✅ | volume_check, watertight |
| camera_cutout | ✅ | volume_check, watertight, camera_hole_section, back_panel_ring |
| port_cutouts | ✅ | overall_bbox, watertight, usbc_slot_void |
| button_slots | ✅ | watertight, mesh_detail |
| deliverable_artifacts | ✅ | step_artifact, stl_artifact |

## Artifacts

| Key | Path |
|-----|------|
| build | `/Users/kuaner/Documents/code/agentcad/examples/iphone15pro-case/models/iphone15pro_case/outputs/build.json` |
| geometry | `/Users/kuaner/Documents/code/agentcad/examples/iphone15pro-case/models/iphone15pro_case/outputs/geometry.json` |
| preview_back | `/Users/kuaner/Documents/code/agentcad/examples/iphone15pro-case/models/iphone15pro_case/outputs/preview.back.svg` |
| preview_iso | `/Users/kuaner/Documents/code/agentcad/examples/iphone15pro-case/models/iphone15pro_case/outputs/preview.iso.svg` |
| step | `/Users/kuaner/Documents/code/agentcad/examples/iphone15pro-case/models/iphone15pro_case/outputs/iphone15pro_case.step` |
| stl | `/Users/kuaner/Documents/code/agentcad/examples/iphone15pro-case/models/iphone15pro_case/outputs/iphone15pro_case.stl` |
| validation | `/Users/kuaner/Documents/code/agentcad/examples/iphone15pro-case/models/iphone15pro_case/outputs/validation.json` |
