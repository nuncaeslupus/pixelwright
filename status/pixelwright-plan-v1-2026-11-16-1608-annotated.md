# Pixelwright — Plan (annotated edition)

> Generated 2026-11-16. This is the document with a **note slot** after every section that has text of its own. Read it in any Markdown app. To annotate, replace the `_(your notes…)_` placeholder under any section. When done, send the file back — notes are acted on.

---

# Plan

## Preamble & scope

**Date**: 2026-11-16
**Specification**: `status/specification.md`
**Author**: Claude (for the repository owner)
**Revision**: 1
**Status**: draft
**Revision log**:
- r1 — first draft

> Review record, kept the way the spec keeps its own: each round of notes bumps
> **Revision** with a log line naming the `<repo>-plan-v<N>-<date>-notes.md`
> export it applied, committed beside this file in the same commit. Approval is
> `approved (YYYY-MM-DD, revision N)`, plus `— without annotations` when there
> were none.

<!-- -->

> **✎ Notes** · `PLAN · intro`
> _(your notes here — replace this line)_

## Technical solution

### Architecture overview

Three layers, one flow (spec §2.2):

- **Core (Python library + `pw`)** owns every file in a project: the project, group and asset
  files, versions, the advice log, normalising, checks, export and `pw wait`. Everything an AI
  or the app does goes through it.
- **App** is a pywebview window started by `pw open`. The page is plain HTML/JS/CSS, as today.
  It calls the core in-process through pywebview's `js_api`, so there is no HTTP server, port or
  token. It has two screens: **Project** (assets by group, each with its state and next step)
  and **Asset** (the image in the centre, a strip of versions, before/after, advice on the
  image, and the actions accept, reject, request, star, approve and open in Aseprite).
- **Agent instructions**: Claude skills for steps 0 and 4 and for the bridge, plus `AGENTS.md`
  for other agents.

<!-- -->

> **✎ Notes** · `PLAN › Architecture overview`
> _(your notes here — replace this line)_

### Data flow

Person or AI → `pw add` (inputs) → `pw normalize` (v001) → `pw check` (script advice) → AI loop
via `pw advice` / fix ops (ai advice, new versions) → app (person accepts or rejects, or leaves a
request) → `pw wait` wakes the AI → … → `pw approve` (final + export).

<!-- -->

> **✎ Notes** · `PLAN › Data flow`
> _(your notes here — replace this line)_

### State changes

| Service | Database | Change | Description |
|---------|----------|--------|-------------|
| Core | Project folder | CREATE | `pixelwright.toml` v2, `group.toml`, `asset.toml`, `advice.jsonl`, `final.png` |
| Core | Project folder | UPDATE | `versions/` gains a file per change; `asset.toml` state, chosen and starred |
| Core | Project folder | DELETE | Only on approve with `keep_all_versions = false`: unstarred middle versions |

<!-- -->

> **✎ Notes** · `PLAN › State changes`
> _(your notes here — replace this line)_

### Technology choices

| Choice | Justification |
|--------|--------------|
| pywebview (≥ 5) | Native window from Python, reuses the HTML/JS UI, runs on Linux (WebKitGTK) and Windows (WebView2) (D-10) |
| `tomllib` + `tomli-w` | TOML for every human-readable file (spec criterion: plain `png`/`toml`/`jsonl`) |
| Polling in `pw wait` (1 s) | Portable across Linux and Windows; inotify is not needed at this scale |

<!-- -->

> **✎ Notes** · `PLAN › Technology choices`
> _(your notes here — replace this line)_

### Reuse map (M0–M3)

| Piece | Fate |
|---|---|
| `core/` (quantize, snap, clean, palette, color, image, checks) | **Keep** as is; normalise and fix ops call it |
| `core/providers/`, `bench/` | **Keep**; optional input source and its benchmark |
| `io/` (png, palette_io, aseprite) | **Keep** |
| `workspace/asset.py` (immutable versions, append-only log, masks) | **Adapt** to `asset.toml` + `advice.jsonl` |
| `workspace/config.py`, `style.py`, `workspace.py` | **Adapt**: palette library, groups, export path, retention; drop roles and stages |
| `workspace/next_step.py` | **Adapt** into `pw status`'s next step per asset |
| `workspace/critique.py`, `budget.py` | **Adapt** critique into AI advice; keep budget |
| `cli/` | **Adapt** to the flow commands; keep the registry and JSON envelope |
| `mcp/server.py` | **Adapt** to the same commands |
| `viewer/server.py` + static (Look/Compare/Mark/Play) | **Replace** by the app; compare, mark and play code is reused inside the Asset screen |
| `viewer/static/blind.*` | **Keep** for the benchmark only |
| `cli/tour.py`, `fixtures/tour.py` | **Replace** by the in-app first run on a sample project |
| `plugin/skills/` | **Rewrite** for the flow; keep the Aseprite plugin |

<!-- -->

> **✎ Notes** · `PLAN › Reuse map (M0–M3)`
> _(your notes here — replace this line)_

### Out of scope

- Game-engine integration beyond the export path (D-4)
- Delta storage of versions (D-13)
- Windows packaging (only the core tests run on Windows)
- New check rules or providers

<!-- -->

> **✎ Notes** · `PLAN › Out of scope`
> _(your notes here — replace this line)_

## Implementation tasks

| T# | Description | Service | Size | Depends | Gate | Tests |
|----|-------------|---------|------|---------|------|-------|
| T52 | Screens review | docs | M | — | owner approves the screens in the reader | none (review artifact) |
| T53 | Project model v2 | core | M | — | `tests_failed == 0` | `test_settings_asset_in_group_uses_group_palette` in `tests/test_project.py` — an asset under a group with `palette = "night"` resolves to the night palette |
| T54 | Asset model v2 | core | M | T53 | `tests_failed == 0` | `test_asset_files_plain_without_app_readable` in `tests/test_asset_model.py` — every file in an asset parses with `tomllib`, `json` and Pillow alone |
| T55 | Advice log | core | M | T54 | `tests_failed == 0` | `test_advice_accept_with_fix_writes_new_version` in `tests/test_advice.py` — accepting advice with a fix adds exactly one version and links it |
| T56 | Promote rejections | core | S | T55 | `tests_failed == 0` | `test_check_promoted_rejection_not_raised_again` in `tests/test_advice.py` — the same rule on the same scope yields no new advice |
| T57 | Flow CLI + MCP | cli | L | T55 | `normalize_seconds <= 5` | `test_normalize_320x180_under_budget` in `tests/test_flow_cli.py` — normalising a 320×180 fixture takes at most 5 s |
| T58 | Version retention | core | S | T57 | `tests_failed == 0` | `test_prune_setting_off_keeps_protected_versions` in `tests/test_retention.py` — after approve only protected versions remain; with the setting on, none are removed |
| T59 | pw wait + hook | core | M | T55 | `wait_latency_seconds <= 10` | `test_wait_request_written_returns_within_latency` in `tests/test_wait.py` — a request written by another process ends `pw wait` within 10 s |
| T60 | App shell | app | M | T52, T53 | `open_50_assets_seconds <= 2` | `test_project_list_50_assets_under_budget` in `tests/test_app_api.py` — the app API lists a 50-asset project in at most 2 s |
| T61 | Project screen | app | M | T60, T57 | `e2e_failed == 0` | `test_project_screen_shows_next_step` in `tests/e2e/test_project_screen.py` — each asset card shows one next step |
| T62 | Asset screen | app | L | T61, T58, T59 | `e2e_failed == 0` | `test_asset_screen_request_creates_pending_advice` in `tests/e2e/test_asset_screen.py` — a request made in the app appears as pending advice with target `ai` |
| T63 | In-app first run | app | M | T62 | owner states what the app does and the next step at each screen without help text | `test_first_launch_opens_sample_project` in `tests/e2e/test_first_run.py` — first launch with no recent projects opens the sample |
| T64 | Agent instructions | plugin | M | T57, T59 | `skills_invalid == 0` | `test_skills_reference_existing_commands` in `tests/test_skills.py` — every `pw` command named in a skill exists |
| T65 | Migrate + clean up | core | M | T63, T64 | `tests_failed == 0` | `test_migrate_m3_workspace_preserves_versions` in `tests/test_migrate.py` — every old version is present and readable after migration |
| T66 | Windows core CI | ci | S | T57 | `windows_core_tests_failed == 0` | none (CI job) |

<!-- -->

> **✎ Notes** · `PLAN › Implementation tasks`
> _(your notes here — replace this line)_

### Task details

- **T52 Screens review**: Screens review: annotated mock-ups of the Project and Asset screens and the first run, in the reader
- **T53 Project model v2**: Project model v2: `pixelwright.toml` (palette library, export path, `keep_all_versions`, rules), `group.toml`, nearest-folder resolution
- **T54 Asset model v2**: Asset model v2: `asset.toml`, `inputs/`, star, chosen, `final.png`; readable with no app
- **T55 Advice log**: Advice log: schema, append, state events, accept runs fix into a new version, reject with reason
- **T56 Promote rejections**: Promote a rejection reason to `style/rules.toml`; `pw check` stops raising it in scope
- **T57 Flow CLI + MCP**: Flow CLI + MCP: `init`, `add`, `normalize`, `check`, `advice`, `star`, `approve` (+ export), `status` with next step
- **T58 Version retention**: Retention: `keep_all_versions = false` prunes on approve, never input, v001, starred or final
- **T59 pw wait + hook**: `pw wait` + Claude session-start hook that reports pending requests
- **T60 App shell**: App shell: `pw open`, pywebview window, open folder, recent projects, DMABUF default on Linux
- **T61 Project screen**: Project screen: assets by group, state, next step and actor
- **T62 Asset screen**: Asset screen: image, versions strip, before/after, advice on image, accept, reject, request to AI, star, approve, open in Aseprite
- **T63 In-app first run**: First run: sample project opened on first launch, guided in the app (replaces `pw tour`)
- **T64 Agent instructions**: Agent instructions: rewrite Claude skills (style, critique-and-fix loop, listen with `pw wait`) and add `AGENTS.md`
- **T65 Migrate + clean up**: `pw migrate` for M0–M3 workspaces; remove the four-mode viewer, `pw tour` and stages; update docs
- **T66 Windows core CI**: Windows CI job running the core tests

**Status legend**: ☐ not started · ◐ in progress · ☑ merged
**Merge order**: T52 and T53 first; then T54 → T55; then T56, T57, T59 in parallel; T58, T60, T66; then T61 → T62 → T63; T64; T65 last
**Branch pattern**: `pw-T<N>-description` from the default branch

<!-- -->

> **✎ Notes** · `PLAN › Task details`
> _(your notes here — replace this line)_

### Dependency graph

```drawspec
{"version": 1, "kind": "flow", "title": "Task dependencies — phases",
 "nodes": [
  {"id": "P1", "text": "Phase 1\nT52, T53, T54, T60, T55, T56, T57,…"},
  {"id": "P2", "text": "Phase 2\nT58, T61, T64, T66, T62, T63, T65"}
 ],
 "edges": [
  {"from": "P1", "to": "P2"}
 ]}
```

**Phase 1** — T52, T53, T54, T60, T55, T56, T57, T59

```drawspec
{"version": 1, "kind": "flow", "title": "Task dependencies — phase 1",
 "nodes": [
  {"id": "T52", "text": "T52\nScreens review"},
  {"id": "T53", "text": "T53\nProject model v2"},
  {"id": "T54", "text": "T54\nAsset model v2"},
  {"id": "T60", "text": "T60\nApp shell"},
  {"id": "T55", "text": "T55\nAdvice log"},
  {"id": "T56", "text": "T56\nPromote rejections"},
  {"id": "T57", "text": "T57\nFlow CLI + MCP"},
  {"id": "T59", "text": "T59\npw wait + hook"}
 ],
 "edges": [
  {"from": "T53", "to": "T54"},
  {"from": "T54", "to": "T55"},
  {"from": "T55", "to": "T56"},
  {"from": "T55", "to": "T57"},
  {"from": "T55", "to": "T59"},
  {"from": "T52", "to": "T60"},
  {"from": "T53", "to": "T60"}
 ]}
```

**Phase 2** — T58, T61, T64, T66, T62, T63, T65 (with T57, T59, T60 from earlier phases)

```drawspec
{"version": 1, "kind": "flow", "title": "Task dependencies — phase 2",
 "nodes": [
  {"id": "T57", "text": "T57\nphase 1"},
  {"id": "T59", "text": "T59\nphase 1"},
  {"id": "T60", "text": "T60\nphase 1"},
  {"id": "T58", "text": "T58\nVersion retention"},
  {"id": "T61", "text": "T61\nProject screen"},
  {"id": "T64", "text": "T64\nAgent instructions"},
  {"id": "T66", "text": "T66\nWindows core CI"},
  {"id": "T62", "text": "T62\nAsset screen"},
  {"id": "T63", "text": "T63\nIn-app first run"},
  {"id": "T65", "text": "T65\nMigrate + clean up"}
 ],
 "edges": [
  {"from": "T57", "to": "T58"},
  {"from": "T57", "to": "T61"},
  {"from": "T60", "to": "T61"},
  {"from": "T58", "to": "T62"},
  {"from": "T59", "to": "T62"},
  {"from": "T61", "to": "T62"},
  {"from": "T62", "to": "T63"},
  {"from": "T57", "to": "T64"},
  {"from": "T59", "to": "T64"},
  {"from": "T63", "to": "T65"},
  {"from": "T64", "to": "T65"},
  {"from": "T57", "to": "T66"}
 ]}
```

<!-- -->

> **✎ Notes** · `PLAN › Dependency graph`
> _(your notes here — replace this line)_

## Evidence log

| T# | Gate | Measured | Command | SHA | Env | Date |
|----|------|----------|---------|-----|-----|------|

<!-- -->

> **✎ Notes** · `PLAN › Evidence log`
> _(your notes here — replace this line)_

## Sign-off

- [ ] Plan approved by the owner
- [ ] Screens approved (T52)
- [ ] Ready for execution

<!-- -->

> **✎ Notes** · `PLAN › Sign-off`
> _(your notes here — replace this line)_

