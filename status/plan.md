# Plan: pixelwright M0-M1 (foundations and MVP pipeline)

**Date**: 2026-11-15
**Specification**: `status/specification.md`
**Author**: Claude (for the repository owner)
**Revision**: 1
**Status**: draft
**Revision log**:
- r1 — first draft: technical solution and the M0-M1 task split; M2-M5 are planned in later design rounds

> Review record, kept the way the spec keeps its own: each round of notes bumps
> **Revision** with a log line naming the `<repo>-plan-v<N>-<date>-notes.md`
> export it applied, committed beside this file in the same commit.

---

## Technical solution

### Architecture overview

One Python package, `pixelwright` (`src/pixelwright/`), with thin front ends over the same functions:

- `core/` — pure functions over an in-memory `IndexedImage` (H x W uint16 indices + `Palette` + optional alpha) and `RGBImage` (generator output): `color` (OKLab/OKLCH), `palette` (I/O, ramps), `snap`, `quantize`, `clean`, `render`, `checks/` (one module per check, common `CheckResult`).
- `workspace/` — `pixelwright.toml`, style guide, asset folders, versions, stages, masks, history, game path mapping, `.gitignore` writer.
- `io/` — PNG (indexed and RGBA), `.aseprite` reader/writer, GPL/HEX palettes.
- `cli/` — `pw` (Typer), JSON envelope.
- `mcp/` — `pw mcp` (official MCP Python SDK, stdio); tool table generated from the same command registry as the CLI, so parity is structural.
- `plugin/` (repository root) — Claude Code plugin (skills, MCP registration) and `plugin/aseprite/` Lua helpers. Skills come in M2; M1 ships only the MCP registration and Lua helpers.

Providers, viewer, animation, scenes and lighting are M2-M5 and get their own plan revisions.

### Data flow

```drawspec
{"version": 1, "kind": "flow", "title": "M1 pipeline",
 "nodes": [
  {"id": "in", "text": "input image\n(sketch / generator output)"},
  {"id": "snap", "text": "snap\nscale + offset, mode per cell"},
  {"id": "quant", "text": "quantize\nOKLab, palette"},
  {"id": "clean", "text": "clean\norphans, AA noise"},
  {"id": "check", "text": "check\nreport.json"},
  {"id": "ver", "text": "version folder\nimage.png, meta.yaml"},
  {"id": "ase", "text": "Aseprite\nretouch"}
 ],
 "edges": [
  {"from": "in", "to": "snap"}, {"from": "snap", "to": "quant"},
  {"from": "quant", "to": "clean"}, {"from": "clean", "to": "check"},
  {"from": "check", "to": "ver"}, {"from": "ver", "to": "ase"},
  {"from": "ase", "to": "ver"}
 ]}
```

Every step reads a version (or input), writes a new version folder with `meta.yaml` (parent, step, params, hashes) and appends to `history.jsonl`. Writes go to a temp folder and are renamed into place.

### State changes

| Service | Database | Change | Description |
|---------|----------|--------|-------------|
| core | workspace files | CREATE | `pixelwright.toml`, `style/`, `experiments/`, `assets/<id>/` per section 5 schemas |
| core | asset folder | CREATE/UPDATE | new version folders (never modified after creation), masks, append-only history |
| core | game repository | UPDATE | `.gitignore` entries for uncommitted stages; exports to mapped game paths |

### Technology choices

| Choice | Justification |
|--------|--------------|
| Python 3.12+, uv, ruff, mypy strict, pytest, Makefile | Owner's standard toolchain (`python-bootstrap` skill) |
| NumPy + Pillow | Pixel arrays and PNG I/O, indexed PNG support |
| scikit-image | Connected components, skeletons, contours for detectors |
| Own OKLab/OKLCH (about 60 lines, vectorized) | Exact control and no heavy dependency; tested against Ottosson's reference values |
| Typer | CLI with typed options; one registry feeds CLI and MCP |
| `mcp` (official Python SDK) | Standard stdio server for Claude Code / Desktop |
| PyYAML + tomllib/tomli-w | Spec and config files |
| Own `.aseprite` codec | Format is documented; avoids depending on an Aseprite binary |
| gitleaks | Secret and personal-data scan in the host gate |

### Out of scope

- Providers and generation, viewer, plugin skills, animation, scenes, lighting, effects, LoRA (M2-M5).
- Any GUI beyond Aseprite helpers.

---

## Implementation tasks

| T# | Description | Service | Size | Depends | Gate | Tests |
|----|-------------|---------|------|---------|------|-------|
| T1 | Scaffold package with uv, ruff, mypy strict, pytest, Makefile (`make check`), GitHub CI, gitleaks; set arsenal `host-gate = "make check"` | repo | S | — | `make_check_exit_code == 0` | `test_package_import_version_matches_pyproject` in `tests/test_meta.py` — `pixelwright.__version__` equals the pyproject version |
| T2 | OKLab/OKLCH conversions and color distance | core.color | S | T1 | `oklab_max_abs_error <= 0.001` | `test_oklab_reference_values_match_published` in `tests/core/test_color.py` — sRGB to OKLab matches Ottosson's published pairs within 1e-3 |
| T3 | Palette model, ramps and I/O (GPL, HEX, `ramps.yaml`) | core.palette, io | S | T2 | `palette_roundtrip_failures == 0` | `test_gpl_roundtrip_preserves_order_and_names` in `tests/io/test_palette_io.py` — write then read returns identical palette |
| T4 | `IndexedImage` / `RGBImage`, PNG I/O (indexed + RGBA), renders (integer upscale, grayscale, value map, overlay) | core.image, core.render | M | T3 | `render_golden_mismatches == 0` | `test_upscale_integer_factor_is_blocky` in `tests/core/test_render.py` — every NxN block of an upscale is one color |
| T5 | Workspace: `pixelwright.toml` roles/paths, stages, `.gitignore` writer, asset folder, versions, `meta.yaml`, `history.jsonl`, masks, schema versioning | workspace | M | T1 | `schema_validation_failures == 0` | `test_new_version_is_immutable_and_logged` in `tests/workspace/test_versions.py` — creating a version writes meta and one history line and never rewrites earlier versions |
| T6 | Style guide format (`style.yaml` @1) and `style_version` on assets; bump and re-check listing | workspace.style | S | T3, T5 | `schema_validation_failures == 0` | `test_style_bump_records_version_on_new_assets` in `tests/workspace/test_style.py` — assets created after a bump carry the new style version |
| T7 | `.aseprite` reader/writer (layers, cels, frames, durations, tags, palette, slices; unknown chunks kept raw) | io.aseprite | L | T4 | `aseprite_roundtrip_failures == 0` | `test_roundtrip_fixture_files_semantically_equal` in `tests/io/test_aseprite.py` — every fixture reads, writes and re-reads to an equal document |
| T8 | Synthetic fixtures: pseudo-pixel generator (upscale x2..x12, blur, sub-cell jitter, JPEG, noise) and detector case format | tests.fixtures | M | T4 | `fixture_cases >= 200` | `test_fixture_generator_is_deterministic` in `tests/fixtures/test_synth.py` — same seed gives byte-identical cases |
| T9 | `snap`: scale and offset detection, mode-per-cell downsample, confidence | core.snap | M | T8 | `snap_scale_exact_rate >= 0.98` | `test_snap_recovers_scale_on_synthetic_set` in `tests/core/test_snap.py` — scale exact on >= 98% and per-pixel accuracy >= 97% |
| T10 | `quantize`: fixed palette (OKLab nearest), discovery (median cut and k-means in OKLab), Bayer dithering inside masks only | core.quantize | M | T3, T4 | `palette_compliance == 1.0` | `test_quantize_fixed_palette_output_fully_in_palette` in `tests/core/test_quantize.py` — every output pixel is a palette index |
| T11 | Checks batch A: `palette`, `grid`, `orphans`, `value-groups`, `focal-contrast`, common `CheckResult` and `report.json` writer | core.checks | M | T4, T8 | `detector_precision_min >= 0.90` | `test_orphans_detector_meets_precision_recall` in `tests/core/checks/test_orphans.py` — precision >= 0.90 and recall >= 0.80 on fixtures |
| T12 | Checks batch B: `line-runs`, `banding` | core.checks | L | T11 | `detector_recall_min >= 0.80` | `test_line_runs_flags_broken_run_sequences` in `tests/core/checks/test_line_runs.py` — 2,1,3,1 runs flagged, 1,1,2,2,3 not |
| T13 | Checks batch C: `pillow`, `ramps`, `dither-zones`, `aa`, `selout`, `outline-share`, `depth-falloff`, `figure-ground`, `diagnostics` | core.checks | L | T11 | `detector_precision_min >= 0.90` | `test_pillow_detector_flags_edge_driven_shading` in `tests/core/checks/test_pillow.py` — outline-inward shading fails, light-vector shading passes |
| T14 | `clean`: orphan removal and AA-noise cleanup driven by detector regions, mask-limited | core.clean | M | T11 | `orphans_after_clean == 0` | `test_clean_removes_orphans_only_inside_mask` in `tests/core/test_clean.py` — orphans inside the mask removed, pixels outside unchanged |
| T15 | CLI `pw` with JSON envelope: init, new, attach, snap, quantize, clean, check, render, diff, mask, approve, reject, export, palette, style, prune | cli | M | T5, T6, T9, T10, T14 | `cli_contract_failures == 0` | `test_cli_json_envelope_on_every_command` in `tests/cli/test_envelope.py` — each command's `--json` output validates against the envelope schema |
| T16 | MCP server `pw mcp` from the same registry; image content for `render` capped at 1024 px | mcp | M | T15 | `cli_mcp_parity_gaps == 0` | `test_every_cli_command_has_matching_mcp_tool` in `tests/mcp/test_parity.py` — tool names and parameters equal the CLI registry |
| T17 | Aseprite bridge: headless export wrapper and Lua helpers (send to pixelwright, load version) in `plugin/aseprite/`; plugin manifest registering the MCP server | io.aseprite, plugin | M | T7, T16 | `lua_helper_tests_failed == 0` | `test_send_to_pixelwright_creates_draft_and_note` in `tests/plugin/test_lua_helpers.py` — running the helper headless writes a draft and a history note (skipped if no Aseprite binary) |
| T18 | Determinism and performance harness: rerun fixture pipelines twice; time local ops | tests.perf | S | T15 | `p95_ms_per_100k_px <= 2000` | `test_pipeline_rerun_is_byte_identical` in `tests/perf/test_determinism.py` — two runs give identical output hashes |

**Status legend**: ☐ not started · ◐ in progress · ☑ merged

**Merge order**: T1; then T2, T5 (parallel); T3; T4, T6; T7, T8, T10; T9, T11; T12, T13, T14; T15; T16; T17, T18
**Branch pattern**: `pw-T<N>-description` from the default branch

### Dependency graph

Generated from the **Depends** column — never drawn by hand.

```drawspec
{"version": 1, "kind": "flow", "title": "Task dependencies — phases",
 "nodes": [
  {"id": "P1", "text": "Phase 1\nT1, T2, T5, T3, T4, T6, T7, T8, T10"},
  {"id": "P2", "text": "Phase 2\nT9, T11, T12, T13, T14, T15, T16, T…"}
 ],
 "edges": [
  {"from": "P1", "to": "P2"}
 ]}
```

**Phase 1** — T1, T2, T5, T3, T4, T6, T7, T8, T10

```drawspec
{"version": 1, "kind": "flow", "title": "Task dependencies — phase 1",
 "nodes": [
  {"id": "T1", "text": "T1\nScaffold package with uv, ruff, myp…"},
  {"id": "T2", "text": "T2\nOKLab/OKLCH conversions and color d…"},
  {"id": "T5", "text": "T5\nWorkspace: pixelwright.toml roles/p…"},
  {"id": "T3", "text": "T3\nPalette model, ramps and I/O (GPL,…"},
  {"id": "T4", "text": "T4\nIndexedImage / RGBImage, PNG I/O (i…"},
  {"id": "T6", "text": "T6\nStyle guide format (style.yaml @1)…"},
  {"id": "T7", "text": "T7\n.aseprite reader/writer (layers, ce…"},
  {"id": "T8", "text": "T8\nSynthetic fixtures: pseudo-pixel ge…"},
  {"id": "T10", "text": "T10\nquantize: fixed palette (OKLab near…"}
 ],
 "edges": [
  {"from": "T1", "to": "T2"},
  {"from": "T2", "to": "T3"},
  {"from": "T3", "to": "T4"},
  {"from": "T1", "to": "T5"},
  {"from": "T3", "to": "T6"},
  {"from": "T5", "to": "T6"},
  {"from": "T4", "to": "T7"},
  {"from": "T4", "to": "T8"},
  {"from": "T4", "to": "T10"}
 ]}
```

**Phase 2** — T9, T11, T12, T13, T14, T15, T16, T18, T17 (with T6, T7, T8, T10 from earlier phases)

```drawspec
{"version": 1, "kind": "flow", "title": "Task dependencies — phase 2",
 "nodes": [
  {"id": "T6", "text": "T6\nphase 1"},
  {"id": "T7", "text": "T7\nphase 1"},
  {"id": "T8", "text": "T8\nphase 1"},
  {"id": "T10", "text": "T10\nphase 1"},
  {"id": "T9", "text": "T9\nsnap: scale and offset detection, m…"},
  {"id": "T11", "text": "T11\nChecks batch A: palette, grid, orph…"},
  {"id": "T12", "text": "T12\nChecks batch B: line-runs, banding"},
  {"id": "T13", "text": "T13\nChecks batch C: pillow, ramps, dith…"},
  {"id": "T14", "text": "T14\nclean: orphan removal and AA-noise…"},
  {"id": "T15", "text": "T15\nCLI pw with JSON envelope: init, ne…"},
  {"id": "T16", "text": "T16\nMCP server pw mcp from the same reg…"},
  {"id": "T18", "text": "T18\nDeterminism and performance harness…"},
  {"id": "T17", "text": "T17\nAseprite bridge: headless export wr…"}
 ],
 "edges": [
  {"from": "T8", "to": "T9"},
  {"from": "T8", "to": "T11"},
  {"from": "T11", "to": "T12"},
  {"from": "T11", "to": "T13"},
  {"from": "T11", "to": "T14"},
  {"from": "T6", "to": "T15"},
  {"from": "T9", "to": "T15"},
  {"from": "T10", "to": "T15"},
  {"from": "T14", "to": "T15"},
  {"from": "T15", "to": "T16"},
  {"from": "T7", "to": "T17"},
  {"from": "T16", "to": "T17"},
  {"from": "T15", "to": "T18"}
 ]}
```

## Evidence log

| T# | Gate | Measured | Command | SHA | Env | Date |
|----|------|----------|---------|-----|-----|------|

---

## Sign-off

- [ ] Design reviewed by the owner
- [ ] Contracts agreed (section 5 of the spec)
- [ ] Migration strategy validated (schema versioning)
- [ ] Ready for execution
