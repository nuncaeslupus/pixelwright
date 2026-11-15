# Specification: pixelwright M3, generation and a guided first run

**Date**: 2026-11-15
**Ticket / PR**: M3 scope (main spec: `status/specification.md`, M3 in §4)
**Author**: Claude (for the repository owner)
**Revision**: 1
**Status**: draft (revision 1)
**Revision log**:
- r1 — first draft: generation providers, `generate` and `regen-region`, cost control, benchmark, and a guided first run

> Review record. Each round of reviewer notes makes a new revision: bump
> **Revision**, add a log line naming the export it applied, and commit that
> export beside this file in the same commit. On approval set **Status** to
> `approved (YYYY-MM-DD, revision N)`.

This spec narrows the main spec to M3. The provider contract (main spec §2.9 and §5,
`Provider`, `GenRequest`, cache, exit codes 5 and 6) stays as written; this file decides
what M3 builds, in what order, and how a first-time user learns the loop.

---

## 1. Problem statement

After M2, pixelwright can clean, check, critique and review an image, but it cannot make
one: every image has to come from outside (`pw attach`). The painter half of the pipeline
(main spec §2.1, "image models paint") is missing, so the loop the tool is built around has
never run end to end.

The second problem is understanding. The artist has used the viewer and the Aseprite bridge
but says the tool does not make sense yet as a whole. The commands are many (about 40) and
each one is small; nothing shows how they chain into "sketch in, game-ready pixel art out",
or what to do next at any point. A tool that only its author's Claude understands fails the
main spec's goal of the artist sketching, approving and retouching.

### Success criteria

- [ ] `pw tour` runs the whole loop (new, attach sketch, generate, snap, quantize, clean,
      check, critique, review in the viewer, approve, export) on a bundled sample, offline,
      with no GPU and no API key, in `<= 60 s` of machine time; each step prints what it did,
      why, and what to look at, in plain words.
- [ ] Every command's `--help` and every viewer screen with nothing to do answers "what
      next?": `pw next <id>` names the next step for an asset from its state, and the viewer
      shows the same hint.
- [ ] `pw generate <id> --provider <p>` makes 1-4 candidate versions with the provider,
      request, seed and cost in each `meta.yaml`; the same request twice is a cache hit
      that costs 0 and gives byte-identical files.
- [ ] Budget: a call that would exceed the workspace's monthly budget is refused before it
      is sent (exit 6); every paid call appears in `pw cost` with its price.
- [ ] Local route: the ComfyUI adapter generates a 320x180 background from a sketch on the
      owner's machine (img2img, Flux or SDXL with a pixel-art LoRA), checked by a prompt the
      owner runs locally.
- [ ] `pw regen-region <id> --issue <n>` repaints only the issue's mask with a provider that
      supports inpainting; pixels outside the mask are unchanged (byte compare).
- [ ] Benchmark: the main spec's criterion (3 generators x 2 chains x 3 briefs x 3 samples,
      `<= 20 USD`, detector scores, Claude pairwise, blind human pairwise ranked with
      Bradley-Terry) produces `benchmarks/<date>/report.html`, and its result sets the
      default provider per asset kind in `pixelwright.toml`.
- [ ] CI stays offline: every adapter is tested against recorded responses; no test needs
      a key, a GPU or the network.

## 2. Systems & Impact

| Component | Change | Notes |
|---|---|---|
| `core/providers/` (new) | Provider protocol, registry, request hashing, cache, retry, budget, cost ledger | Contract from main spec §5 |
| Adapters (new) | `replay` (offline, recorded), `comfyui` (local), `gemini`, `retro-diffusion`, `pixellab`, `gpt-image` | Paid ones gated by the owner's keys (D-M3-1) |
| CLI / MCP | `generate`, `regen-region`, `cost`, `doctor`, `next`, `tour`, `bench run/report/rank` | Same command registry as M1-M2 |
| Workspace | `pixelwright.toml` gets `[providers]`, `[budget]`, `[defaults]`; `cost.jsonl` ledger; keys in git-ignored `.pixelwright/secrets.toml` or env vars | Forward-compatible: old workspaces load with defaults |
| Style guide | `style.yaml` generation presets per provider (prompt preamble, references, LoRA, strength) used by `generate` | Field exists since M1, now read |
| Viewer | Candidates from one `generate` shown side by side in Compare; "what next" hint; blind pairwise page for the benchmark | No generation from the viewer (out of scope) |
| Plugin skills | `first-run` skill (walks a new user through `pw tour` and their first real asset); `review-loop` calls `generate` | |
| Docs | `docs/guide/how-it-works.md`: the loop on one page with one diagram, a glossary (version, stage, issue, check, critique) | Linked from README and `pw --help` |

### Who is affected

- **Artist**: learns the loop from `pw tour` and the guide; decides which paid providers to use.
- **Claude in Claude Code / Desktop**: drives `generate` and `regen-region` through MCP,
  writes prompts from the style presets.
- **Owner's machine**: runs ComfyUI for the local route; no change for anyone else.

## 3. Options

### Option A: Paid APIs first

Build the Gemini, Retro Diffusion and PixelLab adapters first, then the benchmark, then the
local route and the tour.

- Pros: pixel-native providers (Retro Diffusion, PixelLab) may give the best raw output fastest.
- Cons: needs keys and money before anything runs; the tour and CI would depend on recorded
  responses from paid services; the artist still cannot see the loop until late.

### Option B: Learn first, local first, then paid (Recommended)

Order: provider framework with the offline `replay` provider and `pw tour` (the loop runs
end to end on day one, for free), then the local ComfyUI route, then `regen-region`, then
the paid adapters the owner chooses, then the benchmark that picks defaults.

- Pros: the artist sees and understands the loop first; the first real generator is free and
  licence-clear (main spec D-12); paid spend waits for the benchmark, which needs only the
  20 USD already approved.
- Cons: ComfyUI setup on the owner's machine is a manual step; pixel-native paid providers
  are tried later.

### Option C: Every adapter at once, no tour

Build all six adapters in parallel, then the benchmark; leave onboarding to docs.

- Pros: fastest to a complete benchmark.
- Cons: does not answer the understanding problem; most adapter code would be written
  before knowing which providers are worth keeping.

### Comparison

| | A | B | C |
|---|---|---|---|
| Loop visible to the artist | late | first | late |
| Money before first run | yes | no | yes |
| Offline CI | via recordings | native (`replay`) | via recordings |
| Risk of wasted adapters | medium | low | high |

## 4. Recommendation

**Option B.** Milestone order inside M3:

1. **M3a, understand**: provider framework (protocol, registry, cache, budget, cost ledger,
   secrets), the `replay` provider, `pw generate`, `pw next`, `pw doctor`, `pw tour` with a
   bundled sample (sketch and "painted" image drawn procedurally in the repo, so no
   third-party art), `docs/guide/how-it-works.md`, the viewer hint, the `first-run` skill.
2. **M3b, local**: ComfyUI adapter (txt2img, img2img, inpaint) with workflow presets for
   Flux and SDXL plus a pixel-art LoRA, a setup guide, `regen-region`, candidates in Compare.
3. **M3c, paid and benchmark**: the paid adapters chosen in D-M3-1, `pw bench run/report`,
   the blind pairwise page, Bradley-Terry ranking, defaults per asset kind.

### Decisions

| ID | Decision | Status | Date |
|---|---|---|---|
| D-M3-1 | All four paid providers get adapters (Gemini, Retro Diffusion, PixelLab, GPT Image); the owner keeps the ones worth using after the benchmark (cap 20 USD stays) | agreed | 2026-11-15 |
| D-M3-2 | Keys live in env vars or a git-ignored `.pixelwright/secrets.toml`; never in `pixelwright.toml` | proposed | 2026-11-15 |
| D-M3-3 | Monthly budget default 5 USD per workspace, hard stop, `--budget-override` per call needs a flag typed by the user | proposed | 2026-11-15 |
| D-M3-4 | The tour's sample art is generated by code in the repo (no downloaded or copyrighted images) | proposed | 2026-11-15 |
| D-M3-5 | No generation button in the viewer in M3; Claude or the CLI generates, the viewer reviews | proposed | 2026-11-15 |

### Out of scope (M3)

Style LoRA training, animation generation (`animate` mode), scene preview and light zones,
character rigs, a hosted service, any provider without an output licence on record.

**Immediate next action**: on approval, run `design` for the M3 plan (tasks with gates),
then seed the queue.
