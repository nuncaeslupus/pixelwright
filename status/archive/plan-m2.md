# Plan: pixelwright M2 (viewer and critique loop)

**Date**: 2026-11-15
**Specification**: `status/specification.md` (M2 in §4) and `status/viewer/screens.md` (r4, accepted 2026-11-15)
**Author**: Claude (for the repository owner)
**Revision**: 1
**Status**: approved (2026-11-15, revision 1) — without annotations
**Revision log**:
- r1 — first draft: M2 task split (T19-T33). The M0-M1 plan is in `status/archive/plan-m0-m1.md`.

> Review record, kept the way the spec keeps its own: each round of notes bumps
> **Revision** with a log line naming the `<repo>-plan-v<N>-<date>-notes.md`
> export it applied, committed beside this file in the same commit.

---

## Technical solution

### Architecture overview

M2 adds three things on top of the M1 package, all over the same workspace files:

- **Issues and critique** (`workspace/`, `cli/`): an issue is a `masks.yaml` entry with a
  region (mask PNG, box, or the whole image), rule, note, author, version and status.
  `critique.md` gets a parseable format whose complaints point at issues. Stages
  `quantize` and `clean` take `--mask <issue>` and change pixels only inside it.
- **Viewer** (`src/pixelwright/viewer/`): `pw view` serves one page (plain HTML/CSS/JS and
  two OFL font files shipped as package data, no build step) from a stdlib
  `ThreadingHTTPServer` on 127.0.0.1. A small JSON API calls the same functions as the CLI
  command registry, so the viewer adds no business logic of its own.
- **Plugin v0** (`plugin/`): Claude Code skills for art direction (critique protocol, review
  loop, zone-fix loop, style definition) that drive `pw` / `pw mcp`, starting from
  `pw inbox`.

Plus the small M1 leftovers chosen for M2 (`style propose|test`, `palette edit`,
`render --view gif`, `grid` from the CLI) and the gaps found by the real Aseprite test
(`load_version` through the `.aseprite` codec, `palette discover --asset`, positional
`pw init <path>`).

### Data flow

```drawspec
{"version": 1, "kind": "flow", "title": "M2 review loop",
 "nodes": [
  {"id": "cl", "text": "Claude: pw / pw mcp"},
  {"id": "ws", "text": "workspace files"},
  {"id": "vw", "text": "pw view (browser)"},
  {"id": "pp", "text": "person"}
 ],
 "edges": [
  {"from": "cl", "to": "ws", "label": "writes"},
  {"from": "ws", "to": "vw", "label": "polls"},
  {"from": "pp", "to": "vw", "label": "reviews"},
  {"from": "vw", "to": "ws", "label": "writes"},
  {"from": "ws", "to": "cl", "label": "inbox"}
 ]}
```

### State changes

- `masks.yaml` schema `masks@2`: entries gain `version`, `status` (`open` | `fixed`),
  `fixed_in`, `region` (`mask` | `box` | `image`), optional `box`. `masks@1` files read as
  `open`, version unknown, region `mask`; the first write upgrades the file.
- `critique.md`: YAML front matter (`version`, `compared_to`, `verdict`) and one `##` per
  complaint with `issue: <id>`; written by `pw critique write`, parsed for the viewer.
- `history.jsonl`: new events `issue_add`, `issue_resolve`, `decision_revert`; existing
  events unchanged.
- `asset.yaml`: `palette` set by `pw palette discover --asset`.

### Contracts

HTTP API (`pw view`, all JSON except images; every write needs header `X-PW-Token`, the
per-run token embedded in the page; requests with a non-local peer or a `Host` other than
`127.0.0.1:<port>` / `localhost:<port>` get 403):

| Method | Path | Returns / does |
|---|---|---|
| GET | `/api/assets` | cards: id, kind, newest version, stage, status line, thumbnail URL |
| GET | `/api/assets/<id>` | spec, versions (stage, parent, steps), inbox count |
| GET | `/api/assets/<id>/<v>/image.png?view=color\|gray\|values\|silhouette` | native-size PNG |
| GET | `/api/assets/<id>/<v>/report` | `report.json` |
| GET | `/api/assets/<id>/<v>/frames` | frames, durations, tags (from `.aseprite`) |
| GET | `/api/assets/<id>/diff?a=&b=` | changed mask PNG URL, counts, check deltas |
| GET | `/api/assets/<id>/issues?version=` | issues, critique verdict |
| GET | `/api/assets/<id>/history` | history entries, newest first |
| GET | `/api/inbox?since=` | new versions, decisions, issues, notes |
| POST | `/api/assets/<id>/issues` | add (mask PNG base64, box, or none) |
| POST | `/api/assets/<id>/issues/<issue>/resolve` | mark fixed in a version |
| POST | `/api/assets/<id>/<v>/decision` | approve / reject (+ note; reject needs one) |
| POST | `/api/assets/<id>/revert` | log `decision_revert` for the last decision (undo) |

Errors use the CLI envelope's `error.code` / `error.message`. New CLI commands (same
envelope, mirrored in MCP): `issue add|list|resolve`, `critique write|show`, `history`,
`status`, `inbox`, `view [--open]`.

### Technology choices

- Stdlib `http.server` + vanilla JS modules: no web framework, no Node build, nothing new
  to install (`R-FORM-2`, spec §2.8 "no UI framework required").
- Fonts: Atkinson Hyperlegible Next and Mono (OFL), shipped as package data.
- Viewer end-to-end tests with Playwright (dev dependency only; the CI image needs
  Chromium).

### Out of scope

Providers and `generate` (M3); scene preview, light zones, rigs and cross-frame checks
(M4); LoRA (M5); editing pixels in the viewer (never: Aseprite does that).

## Implementation tasks

| T# | Description | Service | Size | Depends | Gate | Tests |
|----|-------------|---------|------|---------|------|-------|
| T19 | Issues model | workspace | S | — | `make_check_exit_code == 0` | `test_masks_v1_reads_as_open_issues` in `tests/workspace/test_issues.py` — a `masks@1` file loads with status open and region mask |
| T20 | Issue and inbox commands | cli, mcp | M | T19 | `make_check_exit_code == 0` | `test_inbox_since_lists_new_versions_and_decisions` in `tests/cli/test_inbox.py` — only events after `--since` are returned |
| T21 | Critique format | workspace, cli | S | T19 | `make_check_exit_code == 0` | `test_critique_roundtrip_keeps_verdict_and_issue_links` in `tests/workspace/test_critique.py` — write then parse gives the same front matter and issue ids |
| T22 | Masked stages | core, cli | M | T19 | `pixels_changed_outside_mask == 0` | `test_clean_with_mask_changes_nothing_outside` in `tests/core/test_masked_stages.py` — quantize and clean with `--mask` leave every pixel outside the mask identical |
| T23 | Diff deltas | cli | S | — | `make_check_exit_code == 0` | `test_diff_reports_check_deltas_and_changed_area` in `tests/cli/test_diff.py` — deltas per check, changed count and bounding box |
| T24 | CLI leftovers | cli, core | M | — | `make_check_exit_code == 0` | `test_render_gif_matches_frame_count_and_durations` in `tests/cli/test_render.py` — GIF has the file's frames and timings; `test_palette_discover_asset_sets_asset_palette`; `test_init_accepts_positional_path` |
| T25 | Bridge on the codec | io, plugin | S | — | `make_check_exit_code == 0` | `test_load_version_prefers_aseprite_file` in `tests/plugin/test_lua_helpers.py` — a version with `image.aseprite` opens with its layers |
| T26 | Style and palette edit | workspace, cli | M | — | `make_check_exit_code == 0` | `test_style_test_reports_per_asset_results` in `tests/cli/test_style.py` — `style test` runs checks on the style's test assets |
| T27 | Viewer server | viewer | L | T20, T21, T23 | `api_endpoints_covered == 13` | `test_write_without_token_is_forbidden` and `test_foreign_host_is_forbidden` in `tests/viewer/test_server.py` — 403 on both; one test per endpoint |
| T28 | Viewer Look | viewer | L | T27 | `e2e_failed == 0` | `test_approve_writes_history_with_measurements` in `tests/viewer/e2e/test_look.py` — clicking Approve logs a decision with the check results |
| T29 | Viewer Compare | viewer | M | T28 | `e2e_failed == 0` | `test_compare_defaults_a_to_latest_approved` in `tests/viewer/e2e/test_compare.py` — A is the newest approved version |
| T30 | Viewer Mark | viewer | M | T28 | `e2e_failed == 0` | `test_saved_mark_is_an_issue_in_native_pixels` in `tests/viewer/e2e/test_mark.py` — the saved mask PNG has the canvas's native size and the drawn pixels |
| T31 | Viewer Play | viewer | M | T28, T25 | `e2e_failed == 0` | `test_play_uses_file_durations` in `tests/viewer/e2e/test_play.py` — frame advance follows the `.aseprite` durations |
| T32 | Viewer polish | viewer | S | T29, T30, T31 | `e2e_failed == 0` | `test_every_control_has_a_title_and_shortcut` in `tests/viewer/e2e/test_a11y.py` — every button has a hover title; every mode reachable by keyboard; both themes render |
| T33 | Plugin v0 skills | plugin | M | T20, T21, T22 | `make_check_exit_code == 0` | `test_plugin_skills_reference_existing_commands` in `tests/plugin/test_skills.py` — every `pw` command a skill names exists in the registry |

### Task details

- **T19 Issues model**: `masks@2` (version, status, fixed_in, region mask/box/image), `Asset.add_issue`, `resolve_issue`, reading `masks@1`.
- **T20 Commands**: `pw issue add|list|resolve`, `pw history`, `pw status <id>`, `pw inbox [--since]`; MCP mirrors from the registry.
- **T21 Critique**: `critique.md` front matter + complaints linked to issues; `pw critique write|show`.
- **T22 Masked stages**: `--mask <issue>` on `quantize` and `clean`; pixels outside unchanged; issue can be resolved by the new version.
- **T23 Diff**: `pw diff` adds per-check deltas, changed pixel count and share, colors used, bounding box.
- **T24 CLI leftovers**: `render --view gif` (GIF and APNG from frames), `check --only grid` on exports, `pw init <path>` positional (keeps `--workspace`), `palette discover --asset` writes `asset.yaml` palette.
- **T25 Bridge**: `load_version.lua` opens `image.aseprite` when present (layers, frames); `send_to_pixelwright` keeps the `.aseprite` alongside the PNG.
- **T26 Style and palette**: `style propose` (palette families and ramps from references), `style test` (checks on the style's test assets), `palette edit` (set, add, remove, reorder colors; ramps re-checked).
- **T27 Viewer server**: `pw view [--port] [--open id/version]`, the API above, token and host checks, static files and fonts as package data.
- **T28 Shell, Assets, Look**: layout, light/dark, top bar, versions strip, status bar (pixel info, view, grid, zoom), Issues/Checks/History panels, decision popover, inbox, shortcuts dialog, 2 s polling.
- **T29 Compare**: side by side (synced), onion, swipe, difference; A/B selection; check deltas.
- **T30 Mark**: brush, rectangle, fill, erase, size; issue form; issue without a mark; undo of strokes and saved issues.
- **T31 Play**: frames strip, play/step, tag, speed, loop, onion skin.
- **T32 Pass**: keyboard reachability, hover titles with shortcuts, both themes, a screenshot per screen for the record.
- **T33 Plugin v0**: skills `art-direction` (critique protocol §2.7), `review-loop` (inbox → critique → issues → masked fixes → checks), `style-definition` (workflow 0); slash commands wrap them.

**Status legend**: ☐ not started · ◐ in progress · ☑ merged

**Merge order**: T19, T23, T24, T25, T26 (parallel); T20, T21, T22 (parallel); T27, T33; T28; T29, T30, T31 (parallel); T32
**Branch pattern**: `pw-T<N>-description` from the default branch

### Dependency graph

Generated from the **Depends** column — never drawn by hand.

```drawspec
{"version": 1, "kind": "flow", "title": "Task dependencies — phases",
 "nodes": [
  {"id": "P1", "text": "Phase 1\nT19, T23, T24, T25, T26, T20, T21,…"},
  {"id": "P2", "text": "Phase 2\nT27, T33, T28, T29, T30, T31, T32"}
 ],
 "edges": [
  {"from": "P1", "to": "P2"}
 ]}
```

**Phase 1** — T19, T23, T24, T25, T26, T20, T21, T22

```drawspec
{"version": 1, "kind": "flow", "title": "Task dependencies — phase 1",
 "nodes": [
  {"id": "T19", "text": "T19\nIssues model"},
  {"id": "T23", "text": "T23\nDiff deltas"},
  {"id": "T24", "text": "T24\nCLI leftovers"},
  {"id": "T25", "text": "T25\nBridge on the codec"},
  {"id": "T26", "text": "T26\nStyle and palette edit"},
  {"id": "T20", "text": "T20\nIssue and inbox commands"},
  {"id": "T21", "text": "T21\nCritique format"},
  {"id": "T22", "text": "T22\nMasked stages"}
 ],
 "edges": [
  {"from": "T19", "to": "T20"},
  {"from": "T19", "to": "T21"},
  {"from": "T19", "to": "T22"}
 ]}
```

**Phase 2** — T27, T33, T28, T29, T30, T31, T32 (with T20, T21, T22, T23, T25 from earlier phases)

```drawspec
{"version": 1, "kind": "flow", "title": "Task dependencies — phase 2",
 "nodes": [
  {"id": "T20", "text": "T20\nphase 1"},
  {"id": "T21", "text": "T21\nphase 1"},
  {"id": "T22", "text": "T22\nphase 1"},
  {"id": "T23", "text": "T23\nphase 1"},
  {"id": "T25", "text": "T25\nphase 1"},
  {"id": "T27", "text": "T27\nViewer server"},
  {"id": "T33", "text": "T33\nPlugin v0 skills"},
  {"id": "T28", "text": "T28\nViewer Look"},
  {"id": "T29", "text": "T29\nViewer Compare"},
  {"id": "T30", "text": "T30\nViewer Mark"},
  {"id": "T31", "text": "T31\nViewer Play"},
  {"id": "T32", "text": "T32\nViewer polish"}
 ],
 "edges": [
  {"from": "T20", "to": "T27"},
  {"from": "T21", "to": "T27"},
  {"from": "T23", "to": "T27"},
  {"from": "T27", "to": "T28"},
  {"from": "T28", "to": "T29"},
  {"from": "T28", "to": "T30"},
  {"from": "T25", "to": "T31"},
  {"from": "T28", "to": "T31"},
  {"from": "T29", "to": "T32"},
  {"from": "T30", "to": "T32"},
  {"from": "T31", "to": "T32"},
  {"from": "T20", "to": "T33"},
  {"from": "T21", "to": "T33"},
  {"from": "T22", "to": "T33"}
 ]}
```

## Risks

| Risk | Likelihood | Impact | Mitigation | Rollback |
|---|---|---|---|---|
| Viewer write endpoints reachable from another site (CSRF, DNS rebinding) | Med | High | Bind 127.0.0.1, check `Host`, per-run token header, no CORS | Start read-only (`--read-only`) |
| `masks@2` breaks existing workspaces | Low | Med | Read `@1` forever; upgrade on first write; fixture test | Writer can emit `@1` again |
| Playwright in CI is slow or flaky | Med | Low | One Chromium, `--trace off`, e2e in its own job; unit tests cover the API | Mark e2e job non-blocking while fixing |
| Masked stages leak changes at mask edges | Med | Med | Gate measures pixels changed outside the mask = 0 | Revert the version; history keeps the parent |
| Viewer grows into an editor | Low | Med | Spec rule: never edits pixels; review checks the API has no pixel writes | — |

## Evidence log

| T# | Gate | Measured | Command | SHA | Env | Date |
|----|------|----------|---------|-----|-----|------|

---

## Sign-off

- [ ] Design reviewed by the owner
- [ ] Contracts agreed (API table above, `masks@2`, `critique.md`)
- [ ] Migration strategy validated (`masks@1` read forever)
- [ ] Ready for execution
