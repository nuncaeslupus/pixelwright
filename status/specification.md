# Specification: pixelwright, a tool that turns any image into game-ready pixel art

**Date**: 2026-11-16
**Ticket / PR**: product re-specification (what & why)
**Author**: Claude (for the repository owner)
**Revision**: 3
**Status**: approved (2026-11-17, revision 3) — without annotations
**Revision log**:
- r1 — first draft, from the re-specification brainstorm (decisions D-1 to D-10 below). Replaces the
  pipeline specification, archived at `status/archive/specification-v1-pipeline.md`.
- r2 — applied `pixelwright-spec-v1-2026-11-16-1656-notes.md` (3 notes): any AI agent as the
  AI actor, with Claude's tools used first; keeping every version is a setting, on by default;
  palettes per asset or group; plain PNG versions with delta storage deferred (D-11 to D-13)
- r3 — aligned with the approved app screens (`status/screens/screens.md` r6, D-14 to D-17):
  advice becomes issues and fixes (`issues.jsonl`, fix candidates as images, replies); groups
  are called categories and carry the asset kind; "approve" becomes **finish**; undo/redo;
  everything saved into the project folder is picked up and processed

> Review record. Each round of reviewer notes makes a new revision: bump
> **Revision**, add a log line naming the export it applied, and commit that
> export beside this file in the same commit. On approval set **Status** to
> `approved (YYYY-MM-DD, revision N)`.

This revision covers **what pixelwright is and why** (sections 1–4). How it is built (pywebview
details, queue format, rule engine) comes in sections 5–6 from `design`, and what to reuse from
the M0–M3 code is decided after that.

---

## 1. Problem statement

The M0–M3 build works piece by piece: CLI `pw`, providers, rule checks, a web viewer with four
modes, an Aseprite bridge and Claude skills. As a product, though, it does not explain itself.
After using it, the owner could not say what it is for, how it attaches to a real game project,
which steps are done by scripts, which by AI and which by a person, or in what order the
viewer's modes are meant to be used. A long help menu did not fix that, because the problem is
the product's shape, not its documentation. pixelwright should do one job: **take any image (an
AI output, a hand sketch, a photo, someone else's art) and turn it into game-ready pixel art for
a given project's style, in escalating steps (scripts, then an AI agent, then the person),
keeping its history.** Where the first image came from does not matter; improving it is the point.

**Who uses it**: one person making the art for a game. An AI agent does the reading, critiquing
and fixing. The agent is not fixed: anything that can run `pw` and read images will do. Claude
(Claude Code or Claude Desktop, on the person's own subscription) is the first-class one, and
pixelwright uses its tools where they help, such as background waiting for app requests. There
is no API key, so the app never calls an AI itself. Below, "AI" means that agent.

**Success criteria (measurable)**:

- [ ] A first-time user, given only the app, can state in one sentence what it does and name the
  next step at every screen without the help text (judged by the owner on a first run of a new
  build).
- [ ] Every step of the flow (section 2.2) names exactly one actor (script, AI or person) and
  one place it runs (app, `pw`, AI session, Aseprite); no step is reachable by more than one main
  path (judged by review of the flow table against the app).
- [ ] A project is an ordinary folder: deleting the app leaves every input, version, issue
  and final image readable as plain files (`png`, `toml`, `jsonl`), verified by a test that
  opens a project with no app installed.
- [ ] No version is ever overwritten. With "keep all versions" on (the default),
  `versions_written == versions_on_disk` after any sequence of accept/reject/edit actions; with it
  off, the input, the first version, every starred version and the final are still kept (tests).
- [ ] Opening an existing project folder of 50 assets shows the asset list in `<= 2 s` on the
  owner's Linux machine.
- [ ] Normalising one 320×180 input (resize, palette, grid, clean-up) takes `<= 5 s` without the
  AI.
- [ ] A request left in the app reaches a listening AI session within `<= 10 s`, and costs no
  AI usage while nothing is pending (test with `pw wait`).
- [ ] Finishing an asset copies its final image to the project's configured export path, which
  can point anywhere, including inside a game engine's project (test).
- [ ] The app and core run on Linux; nothing in the core depends on Linux-only libraries, so a
  Windows build needs packaging work only (checked by running the core test suite on Windows
  in CI).

## 2. Systems & Impact

### 2.1 Concepts

| Concept | What it is | On disk |
|---|---|---|
| **Project** | The art for one game. Holds the style: a palette library, canvas sizes, rules, references, export path. | A folder with `pixelwright.toml` and `style/` |
| **Palette** | A named colour set. A game uses several (backgrounds, characters, a night variant). A category sets a default palette; an asset may override it or use more than one. | `style/palettes/*.gpl` |
| **Asset** | One piece of final art: a background, sprite, portrait or animation. | A subfolder under `assets/` |
| **Category** | Related assets (scenes, characters, props). Sets defaults: asset kind, palette, canvas size, checks. Chosen when adding images. | Parent folders (optional `category.toml`), plus optional tags |
| **Input** | Any image the asset starts from or borrows from. | `inputs/` |
| **Version** | Every change makes a new image; none is ever overwritten. Old versions are the history ("this is what the character first looked like"). A project setting, "keep all versions" (on by default), can be turned off to keep only the input, the first version, starred versions and the final. | `versions/v001.png`, … (plus `.aseprite` when edited by hand) |
| **Issue** | Something wrong or improvable in one version: what, where (one or more areas), why (rule or reason), author (script, AI, person), state (open, fixed, rejected + reason), replies. | Entries in `issues.jsonl` |
| **Fix** | A proposed solution to an issue, always computed as a candidate image before anyone decides. Accepting it writes the next version. | `fixes/<id>.png` + an `issues.jsonl` entry |
| **Request** | An issue the person raises for the AI from the app ("look at this outline"). | Issue with author `person`, target `ai` |
| **Final** | The finished version, copied to the export path. | `final.png` |

**Storage of versions.** Versions are plain indexed PNG files, readable by any tool. Pixel art
compresses well: a 320×180 indexed PNG is typically a few KB, so a thousand versions are tens of
MB. Delta storage (keeping only the changed pixels against the previous version) is possible and
is deferred: `design` measures real sizes, and deltas are added only if a project grows past a
set budget, still without losing plain-file readability of the final and starred versions.

Accepting a fix (or several at once) writes the next version; undo steps back. Rejecting a fix
with a reason is recorded, and that reason can be promoted to a project style rule, so the same
issue is not raised again. Replying to a fix asks the AI to revise it. An issue nobody can fix
automatically is fixed outside (Aseprite saves a new version) and then marked fixed.

### 2.2 The flow

| # | Step | Actor | Where | In → Out |
|---|---|---|---|---|
| 0 | Define the style (once per project) | Person + AI, in conversation | AI session | References, intent → `pixelwright.toml`, `style/` |
| 1 | Brief + starting image | Person (or the AI generates one, optional) | App, AI session, or dropping files in `inputs/` | Text + image → `inputs/` |
| 2 | Normalise | Scripts | `pw` | Input → `v001` (size, palette, grid, clean-up) |
| 3 | Check rules | Scripts | `pw` | Version → issues and fix candidates by `script` |
| 4 | Critique and fix | AI, in a bounded loop | AI session using `pw` | Version + issues + brief → issues and fixes by `ai` |
| 5 | Decide | **Person** | **App** | Version vs fix candidate → accept / reject / reply / raise an issue for the AI / open in Aseprite |
| 6 | Finish and export | Person decides, scripts copy | App or `pw` | Version → `final.png` + copy at export path |

Steps 3–5 repeat until the person finishes the asset. A round moves up a step only when the cheaper one
was not enough: scripts always run; the AI runs when rule issues remain or the person asks;
hand editing in Aseprite is the last resort.

**The AI bridge.** The app cannot call an AI, so requests wait in the asset's issue log. The AI
picks them up in one of two ways:
- **Listening.** In an open session, the AI runs `pw wait` in the background. It blocks until a
  request appears, then returns; the AI handles the request and starts listening again. Claude
  Code supports this directly through its background tasks.
- **On demand.** The person says "check pending". With Claude, a session-start hook also says
  how many requests are waiting.

### 2.3 Inside and outside

**Inside pixelwright:**
- Project and asset structure
- Normalising
- Rules, issues and fixes
- Versions
- The app
- Export
- The request queue
- Agent instructions that teach the flow (Claude skills first; a plain `AGENTS.md` for other agents)

**Outside (plugged in, optional):**
- Image-generation models (providers)
- Aseprite, for hand editing
- The AI agent, as the conversation
- The game engine, which only receives files at the export path

### 2.4 Folder layout (starting point, adaptable)

```
my-game-art/                    project
  pixelwright.toml              style + export path
  style/                        palettes/*.gpl, references, style notes
  assets/
    scenes/                     category (optional category.toml: kind, palette, size)
      harbour-night/            asset
      asset.toml                brief, state, final version
      inputs/
      versions/                 v001.png v002.png ...
      fixes/                    fix candidates
      issues.jsonl
      final.png
  export/                       default export path; may point into the engine project instead
```

### 2.5 Systems affected

| System | Type | Role | Needs changes? | Impact | Severity |
|---|---|---|---|---|---|
| Core library + CLI `pw` | Primary | Project/asset model, normalise, rules, versions, issues and fixes, export, `pw wait` | Yes | Workspace model changes to project-folder + asset-folder; issue log is new | High |
| App (today: `pw view` web viewer) | Primary | Browse a project, decide on fixes, finish | Yes | Becomes a desktop window (pywebview) that opens a project folder; the four modes are replaced by the one flow | High |
| Agent instructions (`plugin/`) | Dependent | Teach the AI the flow and the queue | Yes | Rewritten around steps 0, 4 and the bridge | Med |
| Providers | Dependent | Optional source of starting images | Validate only | Become one input source among others | Low |
| Aseprite bridge | Dependent | Hand editing as the last step | Validate only | Opens a version, saves a new one | Low |
| `pw tour` and help text | UI | First-run explanation | Yes | Replaced by an in-app first run on a sample project | Med |
| Game engine | External | Receives final images | No | Undecided; only an export path is needed now | Low |

**Risk if nothing changes**: the tool keeps working but stays unused, because its owner cannot
fit it into making the game.

## 3. Options

### Option A: Keep the current shape, add a guided mode (Conservative)

- **Description**: Leave the CLI, workspace and four-mode web viewer as they are, and add an
  in-app guided walkthrough on top.
- **Scope**: Viewer only.
- **Effort**: Small
- **Tradeoffs**: Cheapest, but treats a shape problem as a documentation problem, which the help
  menu already showed does not work.
- **Compatibility**: Full.

### Option B: One flow around a project folder, desktop app for decisions (Recommended)

- **Description**: Re-centre everything on the project-folder / asset-folder model and the
  six-step flow. The core (`pw`) does every automatic step. The AI works through `pw` from its
  own session and the request queue. The app is a pywebview desktop window that opens a project
  folder, used to brief, decide and approve.
- **Scope**: Core model, app, skills, first-run; providers and the Aseprite bridge mostly kept.
- **Effort**: Large
- **Tradeoffs**: Fixes the root cause and makes the AI/script/person split visible; costs a
  rework of the viewer and the workspace model.
- **Compatibility**: Breaks the M0–M3 workspace layout; no external users, so no migration is
  needed beyond the owner's test assets.

### Option C: Aseprite plugin as the only interface

- **Description**: Drop the app; show issues and finish inside Aseprite.
- **Scope**: Core + Aseprite plugin.
- **Effort**: Medium
- **Tradeoffs**: No new app, but Aseprite's plugin UI is too limited for browsing a project and
  comparing versions, and it ties the tool to one editor.
- **Compatibility**: Breaks the viewer.

### Comparison

| | Option A | Option B | Option C |
|---|---|---|---|
| Effort | Small | Large | Medium |
| Risk | High (does not fix the problem) | Medium | Medium |
| Completeness | Low | High | Medium |
| Compatibility | Full | Breaks workspace layout | Breaks viewer |
| Maintenance | Grows (two shapes) | One shape | Editor-bound |

## 4. Recommendation

**Recommended option**: Option B. It is the only option that answers the original problem
(what it is for, who does each step, where it runs), and the core, providers and Aseprite
bridge carry over.

**Immediate next action**: After this spec is approved, run `design` for sections 5–6: the
project/asset/advice file formats, the `pw` commands of the flow, `pw wait`, the pywebview app
and its screens, then a reuse map of M0–M3 code.

**Open questions**:
- [ ] Game engine: a short survey of adventure-game and general engines after this spec; until
  then only a configurable export path (D-4).
- [ ] App sub-name: plain "pixelwright", or a sub-name such as "pixelwright Desk" (minor; the
  owner accepts either).

**Decisions log** (carried from the brainstorm):

| ID | Decision | Status | Date |
|----|----------|--------|------|
| D-1 | The viewer-validator is a separate tool with its own name | superseded by D-8 | 2026-11-16 |
| D-2 | The input's origin does not matter; the value is turning any image into game-ready pixel art | agreed | 2026-11-16 |
| D-3 | Improvement escalates: scripts always, then Claude, then the person by hand | agreed | 2026-11-16 |
| D-4 | The game engine is undecided; pixelwright only exports to a configurable path | open (research) | 2026-11-16 |
| D-5 | The folder layout is a starting point and stays adaptable; old versions are always kept as the history | agreed | 2026-11-16 |
| D-6 | The app reaches Claude through a request queue; Claude listens with `pw wait` or checks on demand | agreed | 2026-11-16 |
| D-7 | Integration with other tools of the owner (e.g. a script editor) is out of scope for now | agreed | 2026-11-16 |
| D-8 | pixelwright is the whole product (core, skills, app), and the app is also called pixelwright | agreed | 2026-11-16 |
| D-9 | A project is a folder; an asset is a subfolder with its own history | agreed | 2026-11-16 |
| D-10 | The app is a pywebview desktop window; Linux first, Windows kept possible | agreed | 2026-11-16 |
| D-11 | The AI actor is any agent that can run `pw`; Claude is first-class and its tools (background waiting, hooks, skills) are used where they help | agreed | 2026-11-16 |
| D-12 | "Keep all versions" is a project setting, on by default; off keeps input, first, starred and final | agreed | 2026-11-16 |
| D-13 | Palettes form a library; groups set defaults, assets may override or use several. Versions are plain PNG; delta storage only if measured size demands it | agreed | 2026-11-16 |
| D-14 | Advice splits into issues (what is wrong, where) and fixes (candidate images); replies revise a fix; several fixes can be accepted at once; undo/redo | agreed | 2026-11-17 |
| D-15 | Groups are called categories; adding images asks for one, and it sets kind, palette, size and checks | agreed | 2026-11-17 |
| D-16 | "Approve" becomes **Finish** (state Finished): not every project is a game | agreed | 2026-11-17 |
| D-17 | Everything saved into the project folder is picked up and processed by the scripts; the AI reviews on demand ("Review all new with AI") | agreed | 2026-11-17 |

---

## 5. Contracts

### API contracts

#### Project file `pixelwright.toml`

```toml
[project]
name = "my-game-art"
keep_all_versions = true          # D-12; false keeps input, v001, starred and final
export = "export"                 # relative or absolute; may point into an engine project

[canvas]                          # project default, overridden by category.toml / asset.toml
width = 320
height = 180

[palettes]
default = "main"                  # names of style/palettes/<name>.gpl

[rules]                           # rule id -> "error" | "warn" | "off"
"R-PIX-4" = "warn"
```

`category.toml` (optional, any folder under `assets/`) may set `kind`, `palette`, `palettes`,
`[canvas]` and `checks`. The nearest folder wins: asset, then each parent category, then the project.
The app watches the project folder: an image saved under a category becomes an asset and is
processed (normalise, check) without being asked.

#### Asset file `asset.toml`

```toml
kind = "background"               # optional: inherited from the category
brief = "Harbour at night, two moored boats, lamp light"
palettes = ["night"]              # optional override
state = "review"                  # processing | review | finished
final = "v004"                    # version copied to final.png when finished
starred = ["v001", "v003"]
```

#### Issue log `issues.jsonl` (append-only)

Each line is a new issue, a fix candidate, or an event on one of them:

```json
{"id": "i-7f3c", "at": "2026-11-16T15:00:00Z", "version": "v002",
 "author": "script", "target": null, "kind": "rule", "rule": "R-PIX-4",
 "areas": [{"box": [40, 60, 12, 8]}], "message": "Orphan pixels in the hull", "state": "open"}
{"id": "f-01", "at": "2026-11-16T15:00:01Z", "event": "fix", "issue": "i-7f3c",
 "by": "script", "image": "fixes/f-01.png", "op": {"op": "clean", "args": {"box": [40, 60, 12, 8]}}}
{"id": "f-01", "at": "2026-11-16T15:02:00Z", "event": "accepted", "by": "person",
 "result_version": "v003"}
{"id": "i-8a01", "at": "2026-11-16T15:03:00Z", "version": "v003",
 "author": "person", "target": "ai", "kind": "request",
 "areas": [{"mask": "masks/m1.png"}], "message": "Outline too thick here", "state": "open"}
{"id": "i-8a01", "at": "2026-11-16T15:05:00Z", "event": "reply", "by": "person",
 "message": "Keep 5 strokes, just uneven"}
```

- `author`: `script` | `ai` | `person`. `target`: `ai` marks a request (D-6).
- `kind`: `rule` | `critique` | `note` | `request`.
- Issue `state`: `open` → `fixed` (a fix accepted, or marked fixed after an outside edit) |
  `rejected` (with `reason`).
- Fix events: `fix` (a candidate image), `accepted` (writes the next version; several fixes
  accepted together write one version), `rejected` (with `reason`), `undone`.
- `reply` events form the conversation on an issue; a reply to the AI is a pending request.
- A rejection with `promote: true` adds its reason to `style/rules.toml`, and `pw check` stops
  raising that issue for the scope given (asset, category or project).

#### CLI (`pw <command> --json`, existing result envelope kept)

| Step | Command | Effect |
|---|---|---|
| — | `pw init [dir]` | Create a project folder |
| 1 | `pw add <category/asset> --from <image> [--brief "..."]` | Create the asset, copy the image into `inputs/` |
| 2 | `pw normalize <asset> [--input <file>]` | Size, palette, grid, clean-up → new version |
| 3 | `pw check <asset> [--version v]` | Rule checks → `script` issues and fix candidates |
| 4–5 | `pw issues list|raise|reply|reject|mark-fixed <asset> [id]` | Read and change issues; `raise --target ai` is a request |
| 5 | `pw fix accept|reject <asset> <fix-id>...` | Accept one or several fixes → next version |
| 5 | `pw undo|redo <asset>` | Step the asset's last decision back or forward |
| 5 | `pw star <asset> <version>` | Keep a version under `keep_all_versions = false` |
| 6 | `pw finish <asset> [version]` | Write `final.png`, copy it to the export path, prune if set |
| bridge | `pw wait [--timeout s]` | Block until a pending request exists in the project; print it as JSON; exit 0 |
| app | `pw open [dir]` | Open the app on a project |
| optional | `pw generate`, `pw aseprite` | Providers and the Aseprite bridge, as today |

`pw status` prints, for each asset, its state and the single next step with its actor.

### Inter-service contracts

| Caller | Callee | Protocol | Contract | Failure handling |
|--------|--------|----------|----------|-----------------|
| App (pywebview window) | Core | In-process Python API exposed to the page (`js_api`) | Same functions the CLI calls; JSON in and out | Errors are shown inline next to the action, never as a transient toast |
| AI session | Core | `pw` CLI (JSON envelope) or MCP | Commands above | Non-zero exit with an error object |
| App | AI session | Files: `issues.jsonl` request entries and replies | `pw wait` wakes the AI | Requests stay pending until handled; the app shows them as waiting |
| Core | Aseprite | Existing bridge | Open a version, save back as a new version | Unchanged |
| Core | Providers | Existing provider interface | Optional input source | Unchanged |

### Database migrations

| Service | Database | Change | Reversible | Forward-compatible |
|---------|----------|--------|------------|-------------------|
| Core | Workspace files (M0–M3) | `pw migrate` converts `asset.yaml` → `asset.toml`, `history.jsonl` + issues → `issues.jsonl`, roles/stages config → `pixelwright.toml` v2 | yes (old files kept as `.bak`) | no; the owner's test assets only |

## 6. Risks & Validation

| Risk | Likelihood | Impact | Mitigation | Validation |
|------|-----------|--------|------------|------------|
| The rework grows into a second rewrite | Med | High | Reuse map in the plan; core image functions are not touched | Plan review: each task names what it reuses |
| pywebview (WebKitGTK) freezes on Wayland + NVIDIA | Med | Med | Set `WEBKIT_DISABLE_DMABUF_RENDERER=1` by default on Linux | Manual run on the owner's machine |
| `pw wait` misses or double-delivers a request | Low | Med | Requests are only closed by an explicit `done` event; `pw wait` returns every pending request | Unit test with concurrent writers |
| Pruning removes a version the person wanted | Low | High | Pruning only when the setting is off, never touches starred, first or final versions; prune lists before deleting | Unit test on retention |
| The app still needs explaining | Med | High | One flow, one next step per asset, first run on a sample project; screens reviewed before building | Owner's first-run judgement (success criterion 1) |
| Core picks up Linux-only code | Low | Med | Windows CI job on the core tests | CI |
