# Pixelwright — Specification (annotated edition)

> Generated 2026-11-15. This is the document with a **note slot** after every section that has text of its own. Read it in any Markdown app. To annotate, replace the `_(your notes…)_` placeholder under any section. When done, send the file back — notes are acted on.

---

# Specification

## Preamble & scope

**Date**: 2026-11-15
**Ticket / PR**: initial specification
**Author**: Claude (for the repository owner)
**Revision**: 2
**Status**: draft
**Revision log**:
- r1 — first draft, built from the project brief and the research in `docs/research/` (v1.10)
- r2 — applied `pixelwright-spec-v1-2026-11-15-1209-notes.md` (13 notes): sizes are per asset, character-in-scene and lighting, effects, game-repo integration with experiments vs finals, style definition as the first workflow, privacy check without a deny-list, open questions resolved

> Review record. Each round of reviewer notes makes a new revision: bump
> **Revision**, add a log line naming the export it applied, and commit that
> export beside this file in the same commit. On approval set **Status** to
> `approved (YYYY-MM-DD, revision N)`.

Rule ids such as `R-PIX-4` refer to the adopted rules in
`docs/research/pixelart-research_v1.10-source.md` (rendered: `docs/research/pixelart-research.html`).

<!-- -->

> **✎ Notes** · `SPEC · intro`
> _(your notes here — replace this line)_

## §1 Problem statement

Hand-made pixel art at the level of the VGA-era point-and-click adventures (320x200, up to 256 colors, painted backgrounds, expressive animated characters) is slow and laborious, and one artist cannot produce the hundreds of backgrounds, sprites and animations a full adventure game needs. Image models now paint convincing scenes, but their output only looks like pixel art: it ignores the pixel grid and the palette, breaks clusters and lines, and is inconsistent between frames. Claude can direct art and write code but cannot reach that quality by drawing with code alone, and under a Claude Max subscription it cannot be called from a program; it has to drive the tool from Claude Code or Claude Desktop. pixelwright is the tool that closes this gap: a local pipeline in which image models paint, deterministic post-processing turns their output into true pixel art, automatic checks plus Claude's critique find defects region by region, Claude fixes or regenerates those regions, and the human artist sketches, approves and retouches in Aseprite. The research (`docs/research/`) shows this is the same shape as the original LucasArts process (paint, reduce to ~256 colors, retouch by hand at native resolution: `R-STYLE-1`), so quality depends mostly on post-processing, checks and the retouch loop rather than on the generator.

**Success criteria (measurable)**:

- [ ] `palette_compliance == 1.0` and `grid_compliance == 1.0` for every asset exported by `pw export` (every pixel in the asset palette; one logical pixel per cell) (`R-PIX-1`).
- [ ] Grid snap: on the synthetic fixture set (reference pixel art upscaled x2..x12, then blurred, jittered by a sub-cell offset, JPEG-compressed and color-noised), recovered scale is exact in `>= 0.98` of cases and per-pixel color accuracy after snap is `>= 0.97` (`R-POST-1`).
- [ ] Each detector in the check catalog (section 2.6) ships with a labelled fixture set of at least 20 positive and 20 negative cases and reaches `precision >= 0.90` and `recall >= 0.80` on it.
- [ ] Aseprite round-trip: `.aseprite -> pixelwright -> .aseprite` preserves layers, cels, frames, per-frame durations, tags, palette and cel offsets; semantic-equality test passes on all fixtures.
- [ ] Determinism: the same inputs, parameters and provider responses (cached) give byte-identical outputs (`R-POST-4`); checked by re-running the fixture pipelines twice.
- [ ] Parity: every CLI command that changes or inspects an asset has an MCP tool with the same parameters and result schema; a parity test enumerates both.
- [ ] Asset sizes are free per asset (a 16x16 icon, a 48x80 character, a 640x180 scrolling background); nothing in the core assumes a canvas size. Local operations (snap, quantize, all checks, render previews) finish in `p95 <= 2 s` per 100k native pixels on the developer machine (a 320x180 frame is about 58k); provider calls are excluded.
- [ ] Offline: every non-provider feature works with no network and no API keys; CI runs with network disabled.
- [ ] Core test line coverage `>= 0.90`.
- [ ] Benchmark (M3): at least 3 generators x 2 post-processing chains x 3 briefs x 3 samples run for `<= 20 USD` total, producing a report with detector scores, Claude pairwise verdicts and blind human pairwise ranking (Bradley-Terry) (`R-BENCH-1..3`).
- [ ] Quality bar (judged by the owner; sizes are indicative): (a) from a Wacom sketch, one background at the workspace default canvas is approved as "target quality" after `<= 30 min` of human retouch; (b) one character gets an approved walk cycle; (c) that character walking across that background, passing from a lit to a dark zone, is approved as a scene preview with correct palette-mapped lighting; (d) one effect (water, fire or light flicker) is approved. All decisions are logged in the asset history.
- [ ] Effects and lighting keep pixel art intact: every frame produced by `fx`, `light` or `scene` passes `palette` and `grid` checks with the scene palette.
- [ ] Outputs can be still images, animations (sprite sheet + JSON, GIF/APNG, `.aseprite`) or both, and scene previews (character moving through a background) as GIF/APNG/MP4.
- [ ] Privacy: gitleaks runs in the host gate and passes, and the pre-PR review checklist includes "no personal data, no references to unrelated projects". No deny-list of names is committed (a list of words to avoid would itself leak them); an optional personal list may live only outside the repository (for example in the user's home config) and is read by the check if present.

<!-- -->

> **✎ Notes** · `SPEC §1`
> _(your notes here — replace this line)_

## §2 Systems & Impact

Greenfield project: every component is new. "Needs changes" means "to be built".

| System | Type | Role | Needs changes? | Impact | Severity |
|--------|------|------|----------------|--------|----------|
| `pixelwright` core (Python package) | Primary | Image model of an asset, palettes, post-processing, checks, renders, history | Yes | All features depend on it | High |
| CLI `pw` | Primary | Scriptable interface over the core; used by humans, tests and any agent | Yes | First user-facing surface | High |
| MCP server `pw mcp` (stdio) | Primary | Same operations as tools for Claude Code / Claude Desktop under Claude Max | Yes | How Claude drives the tool | High |
| Local web viewer `pw view` | Primary | Versions side by side, overlays, region annotations saved as masks | Yes | Human review and annotation loop | Med |
| Aseprite bridge | Dependent | Read/write `.aseprite` directly; optional headless Aseprite CLI + Lua for previews and exports | Yes | Human retouch round-trip | High |
| Provider adapters | Dependent | Gemini, Retro Diffusion, PixelLab, GPT Image, local ComfyUI (Flux/SDXL + LoRA) | Yes | Generation; costs money | Med |
| Claude Code plugin | Dependent | Thin plugin: art-direction skills (rubric, prompts, workflows) and MCP registration | Yes | Encodes the technique manual for Claude | Med |
| Workspace (asset folders) | Shared resource | Plain files per asset inside the game repository, mapped onto that repository's own directory structure: inputs, spec, experiments, drafts, versions, masks, reports, log, exports | Yes (format) | Single source of truth; must stay stable | High |
| Style guide | Shared resource | Per-project style: palettes, ramps, light and outline conventions, reference set, generation presets | Yes (format) | Drives both generation and checks; versioned | High |
| Aseprite / LibreSprite | Infrastructure | Human editor; Aseprite compiled for personal use or bought | No | External dependency | Low |
| NVIDIA GPU + ComfyUI | Infrastructure | Local generation and, later, style LoRA training | No (setup only) | Free, licence-clear route | Low |

<!-- -->

> **✎ Notes** · `SPEC §2`
> _(your notes here — replace this line)_

### §2.1 Actors and roles

- **Artist (human)**: sketches (Wacom, any raster), picks references, approves or rejects versions, draws annotations, retouches in Aseprite. Owns final taste.
- **Claude (driver)**: art direction (asset spec, prompts, reference choice), runs the pipeline through MCP/CLI, reads check reports, writes pairwise critiques with regions, applies zone fixes, writes animation key specs, keeps assets coherent with the style guide. Never the source of truth for pixel facts (`R-CRIT-1`).
- **Image models (painters)**: produce detail and atmosphere from sketch, references and prompt. Swappable (`R-GEN-1`). How their input is prepared decides how well the output converts to pixel art, so every generation is conditioned on the style guide: style reference images, a prompt preamble, the scene palette (as palette input where the provider supports it, otherwise as a color swatch reference), lighting notes and provider presets. The goal is raw output already close to the target style and palette, so snap and quantize change little; the `style-match` check measures that distance before post-processing.
- **pixelwright (craftsman)**: deterministic transforms, measurements, renders and bookkeeping. Never calls Claude.

<!-- -->

> **✎ Notes** · `SPEC §2.1`
> _(your notes here — replace this line)_

### §2.2 Workflows

All workflows run inside one asset folder and append to its history.

0. **Style definition** (first, per project; revisited when needed): Claude and the artist build the style guide together: mood references (own sketches and approved assets; commercial games only as analysed style notes, `DA-Q003-1`), palette families and ramps proposed by Claude and edited by the artist, light and outline conventions, density and dithering policy, generation presets per provider. Claude produces 3-5 small test assets with it; the artist approves; the style guide gets a version. Every later asset records which style version it used, and a style change can re-check or re-run older assets.
1. **Background from a sketch** (main case): `new` (canvas, palette, light, depth layers) -> attach sketch and style references -> Claude writes the prompt and generation plan -> `generate` (img2img, 1-4 candidates, possibly several providers) -> `snap` (grid detection, mode downsample) -> `quantize` (OKLab, scene palette, dithering off) -> `clean` (orphans, AA noise) -> `check` -> Claude critique (pairwise vs previous best and references, region-tagged) -> human review in the viewer -> zone fixes (`regen-region` with a mask, or Claude's code edit, or human retouch in Aseprite) -> `check` -> `approve` -> `export`.
2. **Background from scratch**: as 1, with Claude composing a value thumbnail (3-5 value groups, focal point, depth layers, `R-VAL-1`, `R-DEPTH-1`) as the img2img input instead of a sketch.
3. **Image to background**: a photo or painting as input; same as 1, with stronger snap/quantize and a style-transfer prompt.
4. **Sprite or prop**: native-size generation (pixel-native providers, `R-GEN-2`) or downscale of a painted image; then selout, silhouette and readability checks (`R-PIX-9`, `R-READ-1`).
5. **Character animation**: Claude writes the key-pose spec and timing chart (`R-ANIM-1`, `R-ANIM-2`); frames come from a part-based rig (layers with pivots, RotSprite rotation, mandatory cleanup: `R-ANIM-3`), from an AI animator driven by a skeleton/pose (`R-ANIM-7`), or from the artist's drawn bases; inbetweens follow; cross-frame checks gate the result (`R-ANIM-4`). Talking and blinking are overlay libraries on the head (`R-ANIM-5`). Templates: walk (side, front, back), talk, pick up / use, turn, idle.
6. **Ambient effects**: palette cycling ranges declared in the palette (`R-STYLE-3`); procedural effects (water ripples, fire, flicker, particles, sway) rendered and quantized to the palette; previewed as animated GIF/APNG.
7. **Zone fix loop**: any complaint (detector, Claude or human annotation) becomes a mask in native pixels with a rule id and a note; fixes run only inside the mask and the checks re-run (`R-CRIT-3`).
8. **Style coherence**: every new asset is checked against the style guide (palette families, ramp rules, outline policy, light conventions, approved reference assets); approved assets become references and, later, LoRA training data.
9. **Character in scene**: place a sprite or animation on a background at a position or along a path; checks for figure-ground contrast, silhouette readability, scale against the scene and style coherence (`R-COLOR-1`, `R-READ-1`); render a scene preview (character walking through the background, with parallax layers if declared).
10. **Scene lighting**: declare light zones on a background (mask + light color/intensity, or palette remap tables); a character crossing them is recolored through palette-mapped lighting (each sprite color maps to a darker/tinted color of its own ramp or the scene palette, never to off-palette colors), so it darkens in shadow and warms near a lamp while staying pixel art. Lit and unlit variants can be exported as palette swaps.
11. **Effects** (`R-STYLE-3`): palette cycling, procedural effects (water, fire, flicker, rain, fog, particles) and lighting changes rendered frame by frame and quantized to the scene palette; any output passes the `palette` and `grid` checks.

<!-- -->

> **✎ Notes** · `SPEC §2.2`
> _(your notes here — replace this line)_

### §2.3 Workspace layout

pixelwright works on a **workspace** that lives in the game repository, not in this repository. Everything is plain files so git, Aseprite, the viewer, the CLI and any Claude session see the same state (`R-FORM-2`).

- **Adapts to the game's structure**: `pixelwright.toml` maps workspace roles to paths in the game repository (where the style guide lives, where asset folders live, and, per asset kind, where final exports go, for example `game/art/backgrounds/`, `game/art/characters/<id>/`). Defaults below apply when nothing is mapped.
- **Experiments vs finals**: every image belongs to one stage: `experiment` (throwaway tries, provider tests), `draft` (candidate versions in the review loop), `approved` (accepted by the artist) and `final` (exported to the game path). The game repository chooses what to commit per stage (`commit = ["approved", "final", "draft"]`); pixelwright writes the matching `.gitignore` entries, so experiments can be kept locally, committed, or pruned with `pw prune`.

```text
workspace/
  pixelwright.toml          # workspace config: canvas defaults, providers, budgets
  style/                    # style guide (versioned)
    style.yaml              # conventions: light, outline, density, dithering, presets
    palettes/               # *.gpl, *.hex, ramps.yaml
    references/             # approved and mood references
    tests/                  # test assets made while defining the style
  experiments/              # free tries not tied to an asset (provider tests, studies)
  assets/
    bg-harbour-night/       # one folder per asset id, chr-hero, fx-torch
      asset.yaml            # asset spec (2.4)
      inputs/               # sketch.png, refs/*.png, notes.md
      drafts/               # quick iterations before a version is worth keeping
      versions/
        v0001/              # one folder per version (stage: draft | approved)
          image.png         # native resolution, indexed to palette
          image.aseprite    # when layers/frames exist
          meta.yaml         # step, parameters, provider, cost, parent version, seed, hashes
          report.json       # check results
          critique.md       # Claude's pairwise critique with regions
      masks/                # annotation and fix masks (PNG, native res) + masks.yaml
      history.jsonl         # append-only log: steps, decisions (approve/reject), human notes
      export/               # final files (or a link to the mapped game path)
  cache/                    # provider responses keyed by request hash (not committed)
```

<!-- -->

> **✎ Notes** · `SPEC §2.3`
> _(your notes here — replace this line)_

### §2.4 Asset spec (asset.yaml)

```yaml
id: bg-harbour-night
kind: background            # background | sprite | prop | animation | effect | tileset
canvas: {width: 320, height: 180}
palette: style/palettes/harbour-night.gpl   # or a budget for discovery: {discover: 48}
light: {direction: [-0.6, -0.8], key: "moonlight, cool", accents: ["warm lamp at window"]}
depth_layers: [foreground, midground, background, sky]   # masks in masks/layers/*.png
focal: {mask: masks/focal.png, note: "the lit tavern door"}
materials:
  wood: {ramp: [3, 7, 12, 18, 25]}          # palette indices, dark to light
  water: {ramp: [40, 41, 42, 43], cycle: true}
dithering: {allowed: false, zones: []}
outline: {backgrounds: none, sprites: selout}
references: [inputs/refs/mood-01.png]
notes: "Night, fog over the water, one warm accent."
checks: {profile: background-default, overrides: {}}
```

<!-- -->

> **✎ Notes** · `SPEC §2.4`
> _(your notes here — replace this line)_

### §2.5 Pipeline stages (core functions)

Each stage is a pure function with saved parameters (`R-POST-4`), callable from CLI and MCP, and can be limited to a mask.

| Stage | Purpose | Defaults and notes |
|---|---|---|
| `generate` | Call a provider (txt2img, img2img, edit with references, inpaint with mask) | Provider chosen per asset kind; request hashed and cached; cost logged |
| `snap` | Detect pseudo-pixel scale and offset; mode-per-cell downsample | Edge-profile autocorrelation; reuse/benchmark unfake, proper-pixel-art, pixel-snapper (`R-POST-1`, `DA-Q006-1`) |
| `quantize` | Map to fixed palette or discover one | OKLab distance; median cut / k-means in OKLab for discovery; dithering off, Bayer only in zones (`R-POST-2`, `R-POST-3`) |
| `clean` | Remove orphans and AA noise; repair line runs | Driven by detector output; conservative by default |
| `ramp` | Build or repair hue-shifted ramps | OKLCH: monotonic L, hue shift band, mid-tone saturation peak (`R-PIX-2`) |
| `rotate` | RotSprite rotation of a part | Followed by `clean` and line repair (`R-ANIM-3`) |
| `compose` | Assemble layers, parts and overlays into frames | Pivots and offsets from the rig file |
| `cycle` / `fx` | Palette cycling and procedural effects | Render to frames or keep as palette ranges |
| `render` | Previews: integer upscale, grayscale, value groups, silhouette, thumbnails, overlays, GIF/APNG | Images Claude and the viewer read |
| `check` | Run the check catalog | Writes `report.json` |
| `export` | Final PNG, indexed PNG, sprite sheet + JSON, `.aseprite`, palette files | Fails if `palette_compliance < 1` |

<!-- -->

> **✎ Notes** · `SPEC §2.5`
> _(your notes here — replace this line)_

### §2.6 Check catalog

Every check returns `pass | warn | fail`, its measurement, and offending regions in native pixel coordinates. Thresholds start as defaults, then are calibrated from approved assets and logged rejections (`R-CRIT-5`, domain rule 2). Detectors own pixel facts; Claude interprets.

| Check id | Rule | Measurement | Default |
|---|---|---|---|
| `palette` | R-PIX-1 | share of pixels in palette; distinct colors vs budget | fail if `< 1.0` |
| `grid` | R-PIX-1 | uniform NxN blocks in upscaled exports | fail if any |
| `value-groups` | R-VAL-1 | k-means on OKLab L, best k by silhouette; area shares | warn if k > 5 |
| `focal-contrast` | R-VAL-1 | max local RMS contrast inside focal mask vs elsewhere | warn if outside |
| `silhouette` | R-READ-1 | rendered silhouette + 25% grayscale thumbnail for critic and human | judged |
| `depth-falloff` | R-DEPTH-1 | RMS contrast and distance-to-sky per depth layer, near to far | warn if not monotonic |
| `figure-ground` | R-COLOR-1 | OKLab ΔL sprite vs local background | warn below calibrated min |
| `ramps` | R-PIX-2 | L monotonic; adjacent hue delta 5-30 deg; no flat ramps | warn |
| `orphans` | R-PIX-3 | orphan pixels and 1-2 px clusters per 16x16 tile | warn above calibrated max |
| `line-runs` | R-PIX-4 | run-length sequences on 1-px lines; L-corners | warn per segment |
| `banding` | R-PIX-5 | parallel boundaries of adjacent ramp colors | warn above calibrated length |
| `pillow` | R-PIX-6 | correlation of L with light projection vs edge distance | fail if edge distance dominates |
| `dither-zones` | R-PIX-7 | ordered-pattern density map outside declared zones | warn |
| `aa` | R-PIX-8 | AA pixels on sprite alpha boundary; AA run length | warn |
| `selout` | R-PIX-9 | outline L/hue vs inner neighbour; pure-black share | report |
| `outline-share` | R-STYLE-4 | outline pixels on backgrounds | report |
| `anim-consistency` | R-ANIM-4 | palette identity, mask volume tolerance, foot lock, per-frame silhouette | fail on palette, warn otherwise |
| `style-match` | R-GEN-1, workflow 0 | OKLab distance of raw generator output to the style palette; share of pixels needing remap | report, calibrated warn |
| `in-scene` | R-COLOR-1, R-READ-1 | figure-ground ΔL and silhouette for a sprite at each placement or path point; scale vs scene | warn |
| `diagnostics` | DA-Q001-2 | saliency peak vs focal mask, spectrum slope | report only |

<!-- -->

> **✎ Notes** · `SPEC §2.6`
> _(your notes here — replace this line)_

### §2.7 Critique protocol

1. `check` runs; `render` produces upscaled crops, grayscale, value-group map and overlays labelled in native coordinates.
2. Claude compares pairwise (new vs previous best, new vs approved references), never gives a bare 1-10 score (`R-CRIT-2`, `DA-Q008-1`).
3. Every complaint names a region (mask or box), the rule id and a proposed fix; Claude writes it to `critique.md` and `masks/`.
4. The human reviews in the viewer: approve, reject, or draw new annotations. Every decision is logged with the measurements (`R-CRIT-4`).
5. Fixes run only inside masks; checks re-run; the loop ends at human approval.

<!-- -->

> **✎ Notes** · `SPEC §2.7`
> _(your notes here — replace this line)_

### §2.8 Interfaces

**CLI** (`pw`, Typer-style, JSON output with `--json`):

`pw init`, `pw new <id> --kind --canvas --palette`, `pw attach <id> <file> [--as sketch|ref]`, `pw generate <id> --provider --mode --prompt-file [--mask] [--n]`, `pw snap`, `pw quantize`, `pw clean`, `pw ramp`, `pw rotate`, `pw compose`, `pw fx`, `pw check <id> [--version]`, `pw render <id> --view upscale|gray|values|silhouette|overlay|gif`, `pw diff <id> <vA> <vB>`, `pw style init|propose|test|bump`, `pw scene <bg> <sprite> --at|--path`, `pw light <bg> zones|apply`, `pw prune --stage experiment`, `pw mask <id> add|list|clear`, `pw approve|reject <id> <version> [--note]`, `pw export <id>`, `pw palette new|import|discover|edit`, `pw ase open|import|export`, `pw bench run|report`, `pw cost`, `pw view`, `pw mcp`.

**MCP tools** (same core functions; names mirror the CLI): `asset_new`, `asset_status`, `asset_attach`, `generate`, `snap`, `quantize`, `clean`, `ramp`, `rotate`, `compose`, `fx`, `check`, `render` (returns image content plus a file path), `diff`, `style_*`, `scene_render`, `light_apply`, `mask_add`, `mask_list`, `decision_log`, `export`, `palette_*`, `aseprite_*`, `bench_*`, `cost_report`. Tools act on assets, regions and palettes, never on single pixels (`R-TOOL-3`, `DA-Q007-2`), except a bounded `pixels_set` for small fixes inside a mask.

**Viewer** (`pw view`, local HTTP on 127.0.0.1, no UI framework required): asset list; version timeline; side-by-side and onion-skin compare; integer zoom with pixel grid; overlays from `report.json`; draw/erase annotation masks with a rule picker and a note; approve/reject buttons that write to `history.jsonl`; animation preview with per-frame timing; scene preview (character moving through a background); stage filter (experiments, drafts, approved, final). The viewer only writes masks and decisions; it never edits pixels (Aseprite does). A screens spec for the viewer is written during M2, before it is built.

<!-- -->

> **✎ Notes** · `SPEC §2.8`
> _(your notes here — replace this line)_

### §2.9 Providers

One adapter interface with capability flags: `img2img`, `references (n)`, `style_refs`, `mask_inpaint`, `palette_input`, `native_size (max)`, `animation`, `price_per_image`, `watermark`, `licence` (`R-GEN-1`). Initial adapters: Gemini image models (painter; reference images; no palette/mask), Retro Diffusion (palette input, img2img strength, references, mask edit), PixelLab (forced palette, inpainting, skeleton animation), GPT Image (to verify), local ComfyUI (Flux/SDXL + pixel-art LoRA; free; later the project style LoRA). API keys from environment variables or a git-ignored file; per-workspace monthly budget with a hard stop; every call logged with cost. Before any provider output enters the game, its output licence is recorded (`R-GEN-3`).

<!-- -->

> **✎ Notes** · `SPEC §2.9`
> _(your notes here — replace this line)_

### §2.10 Aseprite bridge

- Direct read/write of the documented `.aseprite` format from Python (layers, cels, frames, durations, tags, palette, slices) so no Aseprite process is needed for data exchange (`R-TOOL-1`).
- Optional headless Aseprite (`aseprite --batch --script`) for exports and Lua helpers: a small Lua script set that the artist can run inside Aseprite to "send to pixelwright" (save version + note) and "load version".
- LibreSprite and Pixelorama are not targets for v1; files stay standard PNG so they remain usable.

<!-- -->

> **✎ Notes** · `SPEC §2.10`
> _(your notes here — replace this line)_

### §2.11 Non-functional requirements

- Ubuntu first (current LTS); Python 3.12+; installable with `uv` / `pip`; no GPU needed except for the local provider.
- Open-source dependencies preferred; licences of reused snapping/quantization code checked before vendoring.
- Deterministic, reproducible steps; provider responses cached by request hash.
- No Claude API calls anywhere; Claude only drives through MCP/CLI (domain rule 5).
- The repository contains no personal data and no references to other private projects; the game-specific workspace lives outside this repository.
- Images given to Claude via MCP stay small (crops and upscales sized for the vision model) to save tokens.

<!-- -->

> **✎ Notes** · `SPEC §2.11`
> _(your notes here — replace this line)_

### §2.12 Out of scope (v1)

A pixel editor of its own (`DA-Q007-1`); a desktop app (`DA-Q010-1`); training a model from scratch; using screenshots of commercial games as inputs or training data (`DA-Q003-1`); game-engine integration beyond export files.

<!-- -->

> **✎ Notes** · `SPEC §2.12`
> _(your notes here — replace this line)_

## §3 Options

### Option A: CLI + MCP only, Aseprite as the only viewer (Conservative)

- **Description**: core, CLI and MCP server; review happens in Aseprite and in Claude's rendered previews; annotations are drawn as a layer in Aseprite and imported as masks.
- **Scope**: core, CLI, MCP, Aseprite bridge, providers.
- **Effort**: Medium
- **Tradeoffs**: least code; but version comparison, overlays and decision logging are clumsy in Aseprite, and the human review loop (the main quality lever) is slower.
- **Compatibility**: a later viewer can be added without format changes.

<!-- -->

> **✎ Notes** · `SPEC › Option A: CLI + MCP only, Aseprite as the only viewer (Conservative)`
> _(your notes here — replace this line)_

### Option B: Layered tool: core + CLI + MCP + local web viewer + thin Claude Code plugin (Recommended)

- **Description**: everything in section 2, delivered in milestones; the viewer is a small local web app over the same files; the plugin carries the art-direction skills.
- **Scope**: all components in section 2.
- **Effort**: Large (split into milestones M0-M5 below)
- **Tradeoffs**: more code to maintain; gives the fastest review loop and a clean place for annotations; every layer stays optional.
- **Compatibility**: file formats are the contract; each layer can be replaced.

<!-- -->

> **✎ Notes** · `SPEC › Option B: Layered tool: core + CLI + MCP + local web viewer + thin Claude Code plugin (Recommended)`
> _(your notes here — replace this line)_

### Option C: Desktop application with embedded editor

- **Description**: a native app (Qt/Electron) with its own canvas and the pipeline inside.
- **Scope**: everything plus a UI toolkit and editor.
- **Effort**: Large+
- **Tradeoffs**: duplicates Aseprite; Claude still needs MCP/CLI because it cannot be embedded under Claude Max; rejected in research (`DA-Q010-1`, `DA-Q007-1`).
- **Compatibility**: n/a

<!-- -->

> **✎ Notes** · `SPEC › Option C: Desktop application with embedded editor`
> _(your notes here — replace this line)_

### Comparison

| | Option A | Option B | Option C |
|---|---|---|---|
| Effort | Medium | Large (staged) | Very large |
| Risk | Low | Medium | High |
| Completeness | Partial review loop | Full | Full but redundant |
| Compatibility | Upgradable to B | Formats are contract | Closed |
| Maintenance | Low | Medium | High |

<!-- -->

> **✎ Notes** · `SPEC › Comparison`
> _(your notes here — replace this line)_

## §4 Recommendation

**Recommended option**: Option B, built in milestones so that Option A is simply its first half. The research puts quality in post-processing, checks and the review loop; the viewer makes that loop fast, and the plugin turns the technique manual into Claude's working instructions.

**Milestones**:

- **M0 Foundations**: package skeleton, workspace format, asset spec schema, palette I/O (GPL, HEX, ASE palette), OKLab utilities, renders, `.aseprite` read/write, test fixtures (synthetic pseudo-pixel set, labelled detector cases), privacy check in the host gate.
- **M1 MVP pipeline**: style guide format and `pw style` (workflow 0), `snap`, `quantize`, `clean`, `check` (palette, grid, value-groups, orphans, line-runs, banding, pillow, ramps), CLI + MCP parity, Aseprite round-trip, Lua helper scripts.
- **M2 Viewer and critique loop**: viewer screens spec first, then `pw view` with compare, overlays, masks, decisions; region-limited fixes; critique files; plugin v0 with art-direction skills.
- **M3 Providers and benchmark**: Gemini, Retro Diffusion, PixelLab, GPT Image, local ComfyUI adapters with cost control; run the benchmark; choose default provider per asset kind.
- **M4 Animation, scenes and effects**: rig format, RotSprite + cleanup, templates (walk, talk, pick up, turn, idle), overlays for mouths/eyes, cross-frame checks, palette cycling and effects, character-in-scene previews and palette-mapped scene lighting.
- **M5 Style LoRA**: dataset export from 30-100 approved assets; local LoRA training recipe; style-coherence checks against it.

**Immediate next action**: after this spec is approved, run `design` to write sections 5-6 (contracts: workspace and `asset.yaml` schemas, `report.json`, provider interface, MCP tool schemas; risks) and the plan, then queue M0 tasks with gates.

**Open questions**:

- [ ] None blocking. The viewer's screens spec is due in M2.

**Decisions log**:

| ID | Decision | Status | Date |
|----|----------|--------|------|
| D-1 | Hybrid approach: image models paint, fixed post-processing makes true pixel art, Claude art-directs and critiques, the human sketches, approves and retouches | agreed | 2026-11-15 |
| D-2 | Claude drives the tool from Claude Code/Desktop under Claude Max; the tool never calls Claude | agreed | 2026-11-15 |
| D-3 | Own standalone project, not skills inside claude-arsenal; managed with claude-arsenal | agreed | 2026-11-15 |
| D-4 | Aseprite (or LibreSprite) is the editor; no custom editor | agreed | 2026-11-15 |
| D-5 | Ubuntu first; free/open-source or buildable tools preferred | agreed | 2026-11-15 |
| D-6 | Commercial game images are style references only, never copied or used as inputs | agreed | 2026-11-15 |
| D-7 | No model trained from scratch; a style LoRA later from 30-100 approved assets | agreed | 2026-11-15 |
| D-8 | Interchangeable image providers; API budget decided per milestone | agreed | 2026-11-15 |
| D-9 | Form factor: Python core + CLI + local MCP server + local web viewer + thin Claude Code plugin (research Q-010) | agreed | 2026-11-15 |
| D-10 | Name: pixelwright; repository content in English; no personal data or references to other projects in the repository | agreed | 2026-11-15 |
| D-11 | No screenshots review round for this spec (no own UI beyond the viewer) | agreed | 2026-11-15 |
| D-12 | Owner has an NVIDIA GPU: the local ComfyUI provider is in scope | agreed | 2026-11-15 |
| D-13 | Default canvas 320x180, configurable per workspace and free per asset | agreed | 2026-11-15 |
| D-14 | Licence: MIT | agreed | 2026-11-15 |
| D-15 | Aseprite compiled from source for personal use | agreed | 2026-11-15 |
| D-16 | First benchmark budget cap: 20 USD | agreed | 2026-11-15 |
| D-17 | Claude Code plugin lives in this repository (`plugin/`) | agreed | 2026-11-15 |
| D-18 | Style definition is the first workflow of every project, done with AI help, and can change later (versioned) | agreed | 2026-11-15 |
| D-19 | Workspace adapts to the game repository's layout and separates experiments, drafts, approved and final assets | agreed | 2026-11-15 |
| D-20 | No committed deny-list for the privacy check | agreed | 2026-11-15 |
| D-21 | Viewer screens spec deferred to M2 (D-11 holds for this spec) | agreed | 2026-11-15 |


> Sections 5–6 (contracts, risks) are appended by `design`.

<!-- -->

> **✎ Notes** · `SPEC §4`
> _(your notes here — replace this line)_

