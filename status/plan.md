# Plan: pixelwright rework around one flow (M4)

**Date**: 2026-11-16
**Specification**: `status/specification.md`
**Author**: Claude (for the repository owner)
**Revision**: 2
**Status**: approved (2026-11-17, revision 2) — without annotations
**Revision log**:
- M7 rows (T74–T82, spec `status/m7/spec.md`) added 2026-11-18 at the owner's request
- r1 — first draft
- r2 — aligned with the approved screens (spec r3, D-14 to D-17): advice becomes issues and fixes,
  groups become categories, approve becomes finish, undo/redo; T53, T55–T58, T61, T62 updated

> Review record, kept the way the spec keeps its own: each round of notes bumps
> **Revision** with a log line naming the `<repo>-plan-v<N>-<date>-notes.md`
> export it applied, committed beside this file in the same commit. Approval is
> `approved (YYYY-MM-DD, revision N)`, plus `— without annotations` when there
> were none.

---

## Technical solution

### Architecture overview

Three layers, one flow (spec §2.2):

- **Core (Python library + `pw`)** owns every file in a project: the project, category and asset
  files, versions, the issue log, normalising, checks, export and `pw wait`. Everything an AI
  or the app does goes through it.
- **App** is a pywebview window started by `pw open`. The page is plain HTML/JS/CSS, as today.
  It calls the core in-process through pywebview's `js_api`, so there is no HTTP server, port or
  token. It has two screens: **Project** (assets by category, each with its state and next step)
  and **Asset** (the image in the centre, a strip of versions, before/after, issues and fixes on the
  image, and the actions accept, reject, reply, ask the AI, undo, star, finish and open in Aseprite).
- **Agent instructions**: Claude skills for steps 0 and 4 and for the bridge, plus `AGENTS.md`
  for other agents.

### Data flow

Person or AI → `pw add` (inputs) → `pw normalize` (v001) → `pw check` (script issues and fixes) → AI loop
via `pw issues` / `pw fix` (AI issues, fix candidates) → app (person accepts or rejects, or leaves a
request) → `pw wait` wakes the AI → … → `pw finish` (final + export).

### State changes

| Service | Database | Change | Description |
|---------|----------|--------|-------------|
| Core | Project folder | CREATE | `pixelwright.toml` v2, `category.toml`, `asset.toml`, `issues.jsonl`, `fixes/`, `final.png` |
| Core | Project folder | UPDATE | `versions/` gains a file per change; `asset.toml` state, chosen and starred |
| Core | Project folder | DELETE | Only on finish with `keep_all_versions = false`: unstarred middle versions |

### Technology choices

| Choice | Justification |
|--------|--------------|
| pywebview (≥ 5) | Native window from Python, reuses the HTML/JS UI, runs on Linux (WebKitGTK) and Windows (WebView2) (D-10) |
| `tomllib` + `tomli-w` | TOML for every human-readable file (spec criterion: plain `png`/`toml`/`jsonl`) |
| Polling in `pw wait` (1 s) | Portable across Linux and Windows; inotify is not needed at this scale |

### Reuse map (M0–M3)

| Piece | Fate |
|---|---|
| `core/` (quantize, snap, clean, palette, color, image, checks) | **Keep** as is; normalise and fix ops call it |
| `core/providers/`, `bench/` | **Keep**; optional input source and its benchmark |
| `io/` (png, palette_io, aseprite) | **Keep** |
| `workspace/asset.py` (immutable versions, append-only log, masks) | **Adapt** to `asset.toml` + `issues.jsonl` |
| `workspace/config.py`, `style.py`, `workspace.py` | **Adapt**: palette library, categories, export path, retention; drop roles and stages |
| `workspace/next_step.py` | **Adapt** into `pw status`'s next step per asset |
| `workspace/critique.py`, `budget.py` | **Adapt** critique into AI issues and fixes; keep budget |
| `cli/` | **Adapt** to the flow commands; keep the registry and JSON envelope |
| `mcp/server.py` | **Adapt** to the same commands |
| `viewer/server.py` + static (Look/Compare/Mark/Play) | **Replace** by the app; compare, mark and play code is reused inside the Asset screen |
| `viewer/static/blind.*` | **Keep** for the benchmark only |
| `cli/tour.py`, `fixtures/tour.py` | **Replace** by the in-app first run on a sample project |
| `plugin/skills/` | **Rewrite** for the flow; keep the Aseprite plugin |

### Out of scope

- Game-engine integration beyond the export path (D-4)
- Delta storage of versions (D-13)
- Windows packaging (only the core tests run on Windows)
- New check rules or providers

---

## Implementation tasks

| T# | Description | Service | Size | Depends | Gate | Tests |
|----|-------------|---------|------|---------|------|-------|
| T52 | Screens review | docs | M | — | owner approves the screens in the reader | none (review artifact) |
| T53 | Project model v2 | core | M | — | `tests_failed == 0` | `test_settings_asset_in_category_uses_category_palette` in `tests/test_project.py` — an asset under a category with `palette = "night"` resolves to the night palette |
| T54 | Asset model v2 | core | M | T53 | `tests_failed == 0` | `test_asset_files_plain_without_app_readable` in `tests/test_asset_model.py` — every file in an asset parses with `tomllib`, `json` and Pillow alone |
| T55 | Issues and fixes log | core | M | T54 | `tests_failed == 0` | `test_fix_accept_writes_new_version` in `tests/test_issues.py` — accepting a fix adds exactly one version and links it |
| T56 | Promote rejections | core | S | T55 | `tests_failed == 0` | `test_check_promoted_rejection_not_raised_again` in `tests/test_issues.py` — the same rule on the same scope yields no new issue |
| T57 | Flow CLI + MCP | cli | L | T55 | `normalize_seconds <= 5` | `test_normalize_320x180_under_budget` in `tests/test_flow_cli.py` — normalising a 320×180 fixture takes at most 5 s |
| T58 | Version retention | core | S | T57 | `tests_failed == 0` | `test_prune_setting_off_keeps_protected_versions` in `tests/test_retention.py` — after finish only protected versions remain; with the setting on, none are removed |
| T59 | pw wait + hook | core | M | T55 | `wait_latency_seconds <= 10` | `test_wait_request_written_returns_within_latency` in `tests/test_wait.py` — a request written by another process ends `pw wait` within 10 s |
| T60 | App shell | app | M | T52, T53 | `open_50_assets_seconds <= 2` | `test_project_list_50_assets_under_budget` in `tests/test_app_api.py` — the app API lists a 50-asset project in at most 2 s |
| T61 | Project screen | app | M | T60, T57 | `e2e_failed == 0` | `test_project_screen_shows_next_step` in `tests/e2e/test_project_screen.py` — each asset card shows one next step |
| T62 | Asset screen | app | L | T61, T58, T59 | `e2e_failed == 0` | `test_asset_screen_request_creates_open_issue` in `tests/e2e/test_asset_screen.py` — a request made in the app appears as an open issue with target `ai` |
| T63 | In-app first run | app | M | T62 | owner states what the app does and the next step at each screen without help text | `test_first_launch_opens_sample_project` in `tests/e2e/test_first_run.py` — first launch with no recent projects opens the sample |
| T64 | Agent instructions | plugin | M | T57, T59 | `skills_invalid == 0` | `test_skills_reference_existing_commands` in `tests/test_skills.py` — every `pw` command named in a skill exists |
| T65 | Migrate + clean up | core | M | T63, T64 | `tests_failed == 0` | `test_migrate_m3_workspace_preserves_versions` in `tests/test_migrate.py` — every old version is present and readable after migration |
| T66 | Windows core CI | ci | S | T57 | `windows_core_tests_failed == 0` | none (CI job) |
| T67 | Generation on v2 | core | L | T65 | `tests_failed == 0` | `test_generate_adds_inputs_and_versions` in `tests/test_generate_v2.py` — a replay provider's images become inputs, then normalised versions; cost is logged |
| T68 | Bench on v2 | core | M | T67 | `tests_failed == 0` | `test_bench_run_on_project` in `tests/bench/test_run.py` — a matrix run on a v2 project scores every provider + chain |
| T69 | Remove the old workspace | core | L | T67, T68 | `tests_failed == 0` | `test_no_workspace_package` in `tests/test_meta.py` — `pixelwright.workspace` no longer exists and every command runs on a v2 project |
| T70 | Fractional pixel scale | core | M |  | `grid_drift_px <= 0.5` | `test_snap_recovers_non_integer_scale` in `tests/core/test_snap.py` — art upscaled by 8.6 is snapped back to its native size with dither and diagonals intact |
| T71 | Paintings to readable pixels | core | L | T70 | `stray_cluster_share <= 0.02` | `test_painting_regions_are_flat` in `tests/core/test_abstract.py` — after normalise, at most 2% of pixels sit in same-colour clusters of 1-4 pixels |
| T72 | Clean diagonals | core | M | T70 | `irregular_line_steps == 0` | `test_diagonals_regularised` in `tests/core/test_lines.py` — jagged 1-px lines become regular 1:1 / 2:1 / 1:2 steps |
| T73 | Game style kit | core | L | T71 | `tests_failed == 0` | `test_generate_sends_style_kit` in `tests/test_style_kit.py` — the request carries the palette hex codes, pixel size, rules and reference images |
| T74 | Scene file and scale model | core | M |  | `tests_failed == 0` | `test_person_height_follows_horizon` in `tests/test_scene.py` — a door 60 px tall at row 170, horizon 70, gives a 51 px person there and 25.5 px at row 120 |
| T75 | Compose layers with contact shadows | core | L | T74 | `tests_failed == 0` | `test_shadow_uses_scene_colours` in `tests/test_scene.py` — no colour outside the background and layers |
| T76 | Character sizes by depth | core | M | T75 | `tests_failed == 0` | `test_actor_size_picked_by_depth_without_resampling` in `tests/test_scene.py` — a far character uses the small asset pixel for pixel |
| T77 | Props with the scene camera | core | S | T74 | `tests_failed == 0` | `test_generate_scene_adds_camera_and_size` in `tests/test_scene.py` — the prompt names camera, horizon and target height |
| T78 | Scrolling scenes joined by seam | core | M | T75 | `tests_failed == 0` | `test_seam_cut_follows_low_error` in `tests/core/test_seam.py` — the seam passes where tiles agree, no new colour |
| T79 | Object states and animation | core | M | T75 | `tests_failed == 0` | `test_state_switch_and_frames` in `tests/test_scene.py` — a state switch changes only that layer; GIF frames = longest strip |
| T80 | ComfyUI ControlNet from a sketch | core | M |  | `tests_failed == 0` | `test_controlnet_workflow_carries_sketch` in `tests/core/test_comfyui.py` — the ControlNet node is fed by the uploaded sketch |
| T81 | Real crypt scene on Retro Diffusion | docs | S | T76, T77, T79 | owner judges the composed scene (about $0.5, owner OK first) | none (manual) |
| T82 | Local route quality on the GPU | docs | M | T80, #119 | owner judges local against Retro Diffusion | none (manual) |

### Task details

- **T52 Screens review**: Screens review: annotated mock-ups of the Project and Asset screens and the first run, in the reader
- **T53 Project model v2**: Project model v2: `pixelwright.toml` (palette library, export path, `keep_all_versions`, rules), `category.toml` (kind, palette, canvas, checks), nearest-folder resolution
- **T54 Asset model v2**: Asset model v2: `asset.toml`, `inputs/`, star, chosen, `final.png`; readable with no app
- **T55 Issues and fixes log**: Issues and fixes log (`issues.jsonl`): schema, append, events; fix candidates as images; accepting one or several fixes writes one new version; reject with reason; reply; mark fixed; undo/redo
- **T56 Promote rejections**: Promote a rejection reason to `style/rules.toml`; `pw check` stops raising it in scope
- **T57 Flow CLI + MCP**: Flow CLI + MCP: `init`, `add`, `normalize`, `check`, `issues`, `fix`, `undo`/`redo`, `star`, `finish` (+ export), `status` with next step
- **T58 Version retention**: Retention: `keep_all_versions = false` prunes on finish, never input, v001, starred or final
- **T59 pw wait + hook**: `pw wait` + Claude session-start hook that reports pending requests
- **T60 App shell**: App shell: `pw open`, pywebview window, open folder, recent projects, DMABUF default on Linux
- **T61 Project screen**: Project screen: assets by category with filters (waiting on, state), state, next step and actor; add dialog with category; folder watching
- **T62 Asset screen**: Asset screen per `status/screens/screens.md`: image with Move/Select tools and zoom to area, versions strip, compare (hold Space, side by side), issues and fixes on the image, accept (several at once), reject, reply, ask the AI, undo/redo, star, finish, open in Aseprite, mark fixed
- **T63 In-app first run**: First run: sample project opened on first launch, guided in the app (replaces `pw tour`)
- **T64 Agent instructions**: Agent instructions: rewrite Claude skills (style, critique-and-fix loop, listen with `pw wait`) and add `AGENTS.md`
- **T65 Migrate + clean up**: `pw migrate` for M0–M3 workspaces; remove the four-mode viewer, `pw tour` and stages; update docs
- **T66 Windows core CI**: Windows CI job running the core tests
- **T67 Generation on v2**: `pw generate <asset>` runs a provider; its images land in `inputs/` and the scripts normalise each into a version. `pw generate <asset> --issue <id>` repaints the issue's areas and proposes the result as a fix. Providers, defaults and the monthly budget are read from `pixelwright.toml`; `pw cost` and `pw doctor` work on the project
- **T68 Bench on v2**: `pw bench` builds its assets in a v2 project (`assets/bench/...`), runs the chains through normalise and check, and ranks as before
- **T69 Remove the old workspace**: Delete `pixelwright.workspace` and the M0–M3 commands (stages, approve/reject/export, masks, critique, inbox, next, render, diff, `init --legacy`); `pw palette import` writes to `style/palettes/`; the Aseprite bridge sends versions to v2 assets; `pw migrate` keeps reading old workspaces
- **T70 Fractional pixel scale**: `snap` detects and resamples non-integer pixel sizes (e.g. 2752 px / 320 = 8.6), so the grid does not drift across the image and dither checkerboards and diagonals survive. Integer scales keep today's behaviour.
- **T71 Paintings to readable pixels**: For images reduced to the canvas (no pixel grid): edge-preserving simplification (Kuwahara or mean-shift) before reducing, then removal of small same-colour clusters (2-4 px, not only single orphans) that carry no shape. Accents from `core/importance` are protected. Evaluate region-based abstraction (Gerstner et al., *Pixelated Image Abstraction*) and keep it if it reads better on the test painting.
- **T72 Clean diagonals**: A fixer for what `check_line_runs` (R-PIX-4) flags: one-pixel outlines with irregular step lengths are redrawn with consistent steps (1:1, 2:1, 1:2...) along the same path, as a script fix the person can accept or reject.
- **T73 Game style kit**: One style kit per project (and per category): palette, native size, pixel rules, reference images in `style/references/` and a prompt preamble. `pw generate` always sends it (palette as hex codes or provider palette input, references as image inputs where supported), and normalise uses the same palette and canvas, so 'for my game, an empty old bar with a stage and a piano under spotlights' comes back in the game's style. `pw style show` prints the kit.

**Status legend**: ☐ not started · ◐ in progress · ☑ merged
**Merge order**: T52 and T53 first; then T54 → T55; then T56, T57, T59 in parallel; T58, T60, T66; then T61 → T62 → T63; T64; T65 last
**Branch pattern**: `pw-T<N>-description` from the default branch

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
  {"id": "T55", "text": "T55\nIssues and fixes log"},
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

## Evidence log

| T# | Gate | Measured | Command | SHA | Env | Date |
|----|------|----------|---------|-----|-----|------|

---

## Sign-off

- [ ] Plan approved by the owner
- [x] Screens approved (T52)
- [ ] Ready for execution
