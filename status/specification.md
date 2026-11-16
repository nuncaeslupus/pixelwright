# Specification: pixelwright, a tool that turns any image into game-ready pixel art

**Date**: 2026-11-16
**Ticket / PR**: product re-specification (what & why)
**Author**: Claude (for the repository owner)
**Revision**: 1
**Status**: draft
**Revision log**:
- r1 — first draft, from the re-specification brainstorm (decisions D-1 to D-10 below). Replaces the
  pipeline specification, archived at `status/archive/specification-v1-pipeline.md`.

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
which steps are done by scripts, which by Claude and which by a person, or in what order the
viewer's modes are meant to be used. A long help menu did not fix that, because the problem is
the product's shape, not its documentation. pixelwright should do one job: **take any image (an
AI output, a hand sketch, a photo, someone else's art) and turn it into game-ready pixel art for
a given project's style, in escalating steps (scripts, then Claude, then the person), keeping
every version.** Where the first image came from does not matter; improving it is the point.

**Who uses it**: one person making the art for a game. Claude does the reading, critiquing and
fixing through the person's own Claude subscription (Claude Code or Claude Desktop); there is
no API key, so the app never calls Claude itself.

**Success criteria (measurable)**:

- [ ] A first-time user, given only the app, can state in one sentence what it does and name the
  next step at every screen without the help text (judged by the owner on a first run of a new
  build).
- [ ] Every step of the flow (section 2.2) names exactly one actor (script, Claude or person) and
  one place it runs (app, `pw`, Claude, Aseprite); no step is reachable by more than one main
  path (judged by review of the flow table against the app).
- [ ] A project is an ordinary folder: deleting the app leaves every input, version, advice entry
  and final image readable as plain files (`png`, `toml`, `jsonl`), verified by a test that
  opens a project with no app installed.
- [ ] No version is ever overwritten: `versions_written == versions_on_disk` after any sequence
  of accept/reject/edit actions (test).
- [ ] Opening an existing project folder of 50 assets shows the asset list in `<= 2 s` on the
  owner's Linux machine.
- [ ] Normalising one 320×180 input (resize, palette, grid, clean-up) takes `<= 5 s` without
  Claude.
- [ ] A request left in the app reaches a listening Claude session within `<= 10 s`, and costs no
  Claude usage while nothing is pending (test with `pw wait`).
- [ ] Approving an asset copies its final image to the project's configured export path, which
  can point anywhere, including inside a game engine's project (test).
- [ ] The app and core run on Linux; nothing in the core depends on Linux-only libraries, so a
  Windows build needs packaging work only (checked by running the core test suite on Windows
  in CI).

## 2. Systems & Impact

### 2.1 Concepts

| Concept | What it is | On disk |
|---|---|---|
| **Project** | The art for one game. Holds the style: palette, canvas sizes, rules, references, export path. | A folder with `pixelwright.toml` and `style/` |
| **Asset** | One piece of final art: a background, sprite, portrait or animation. | A subfolder under `assets/` |
| **Group** | Related assets (a scene, a character). | Parent folders, plus optional tags |
| **Input** | Any image the asset starts from or borrows from. | `inputs/` |
| **Version** | Every change makes a new image; none is ever overwritten. Old versions are the history ("this is what the character first looked like"). | `versions/v001.png`, … (plus `.aseprite` when edited by hand) |
| **Advice** | One observation on one version: what is wrong, where (region), why (rule or reason), proposed fix, author (script, Claude, person), state (pending, accepted, rejected + reason). | One line in `advice.jsonl` |
| **Request** | A piece of advice addressed to Claude from the app ("Claude, look at this outline"). | Advice with author `person`, target `claude`, state `pending` |
| **Final** | The approved version, copied to the export path. | `final.png` |

Accepting advice applies its fix and creates a new version. Rejecting advice with a reason is
recorded, and that reason can be promoted to a project style rule, so the same advice is not
given again.

### 2.2 The flow

| # | Step | Actor | Where | In → Out |
|---|---|---|---|---|
| 0 | Define the style (once per project) | Person + Claude, in conversation | Claude | References, intent → `pixelwright.toml`, `style/` |
| 1 | Brief + starting image | Person (or Claude generates one, optional) | App, Claude, or dropping files in `inputs/` | Text + image → `inputs/` |
| 2 | Normalise | Scripts | `pw` | Input → `v001` (size, palette, grid, clean-up) |
| 3 | Check rules | Scripts | `pw` | Version → advice by `script` |
| 4 | Critique and fix | Claude, in a bounded loop | Claude using `pw` | Version + advice + brief → advice by `claude` + new versions |
| 5 | Decide | **Person** | **App** | Before/after + advice → accept / reject / own notes / request to Claude / open in Aseprite |
| 6 | Approve and export | Person decides, scripts copy | App or `pw` | Version → `final.png` + copy at export path |

Steps 3–5 repeat until the person approves. A round moves up a step only when the cheaper one
was not enough: scripts always run; Claude runs when rule advice remains or the person asks;
hand editing in Aseprite is the last resort.

**The Claude bridge.** The app cannot call Claude, so requests wait in the asset's advice log.
Claude picks them up in one of two ways:
- **Listening.** In an open Claude session, Claude runs `pw wait` in the background. It blocks
  until a request appears, then returns; Claude handles the request and starts listening again.
- **On demand.** The person says "check pending", and a session-start hook tells Claude how many
  requests are waiting.

### 2.3 Inside and outside

**Inside pixelwright:**
- Project and asset structure
- Normalising
- Rules and advice
- Versions
- The app
- Export
- The request queue
- Claude skills that teach the flow

**Outside (plugged in, optional):**
- Image-generation models (providers)
- Aseprite, for hand editing
- Claude, as the conversation
- The game engine, which only receives files at the export path

### 2.4 Folder layout (starting point, adaptable)

```
my-game-art/                    project
  pixelwright.toml              style + export path
  style/                        palette.gpl, references, style notes
  assets/
    scenes/harbour-night/       asset (parent folders are groups)
      asset.toml                brief, state, chosen version
      inputs/
      versions/                 v001.png v002.png ...
      advice.jsonl
      final.png
  export/                       default export path; may point into the engine project instead
```

### 2.5 Systems affected

| System | Type | Role | Needs changes? | Impact | Severity |
|---|---|---|---|---|---|
| Core library + CLI `pw` | Primary | Project/asset model, normalise, rules, versions, advice, export, `pw wait` | Yes | Workspace model changes to project-folder + asset-folder; advice log is new | High |
| App (today: `pw view` web viewer) | Primary | Browse a project, decide on advice, approve | Yes | Becomes a desktop window (pywebview) that opens a project folder; the four modes are replaced by the one flow | High |
| Claude skills (`plugin/`) | Dependent | Teach Claude the flow and the queue | Yes | Rewritten around steps 0, 4 and the bridge | Med |
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
  six-step flow. The core (`pw`) does every automatic step. Claude works through `pw` from its
  own session and the request queue. The app is a pywebview desktop window that opens a project
  folder, used to brief, decide and approve.
- **Scope**: Core model, app, skills, first-run; providers and the Aseprite bridge mostly kept.
- **Effort**: Large
- **Tradeoffs**: Fixes the root cause and makes the AI/script/person split visible; costs a
  rework of the viewer and the workspace model.
- **Compatibility**: Breaks the M0–M3 workspace layout; no external users, so no migration is
  needed beyond the owner's test assets.

### Option C: Aseprite plugin as the only interface

- **Description**: Drop the app; show advice and approve inside Aseprite.
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

---

> Sections 5–6 (contracts, risks) are appended by `design`.
