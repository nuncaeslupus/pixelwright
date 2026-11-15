# Pixelwright — Plan (annotated edition)

> Generated 2026-11-15. This is the document with a **note slot** after every section that has text of its own. Read it in any Markdown app. To annotate, replace the `_(your notes…)_` placeholder under any section. When done, send the file back — notes are acted on.

---

# Plan

## Preamble & scope

**Date**: 2026-11-15
**Specification**: `status/m3/spec.md` (r1, approved 2026-11-15); provider contract in `status/specification.md` §2.9 and §5
**Author**: Claude (for the repository owner)
**Revision**: 1
**Status**: draft
**Revision log**:
- r1 — first draft: M3 task split (T34-T51). The M2 plan is in `status/archive/plan-m2.md`.

> Review record, kept the way the spec keeps its own: each round of notes bumps
> **Revision** with a log line naming the `<repo>-plan-v<N>-<date>-notes.md`
> export it applied, committed beside this file in the same commit.

<!-- -->

> **✎ Notes** · `PLAN · intro`
> _(your notes here — replace this line)_

## Technical solution

### Architecture overview

M3 adds a painter in front of the M1-M2 pipeline and a guide around it:

- **Providers** (`src/pixelwright/core/providers/`): the `Provider` protocol, `GenRequest`,
  `GenResult`, `Capabilities` and `Cost` from the main spec §5; a registry by name; a
  request hasher (canonical JSON plus SHA-256 of every input image); a file cache in the
  workspace `cache/`; retry 2x with backoff on 429/5xx; a budget guard and a cost ledger.
  Adapters are one module each: `replay`, `comfyui`, `gemini`, `retro_diffusion`,
  `pixellab`, `gpt_image`. HTTP goes through one small client (`urllib`, injectable
  transport) so tests replay recorded responses and never touch the network.
- **Generation commands** (`cli/`, `mcp/`): `generate` and `regen-region` write candidate
  versions through the existing `Asset` API, reading the style guide's generation preset
  for the provider. `cost`, `doctor` and `next` are read-only.
- **Guided first run**: `pw tour` builds a workspace in a temp or given folder from a
  bundled sample drawn by code (`fixtures/tour.py`), runs every step with the `replay`
  provider, prints a short "what happened / why / look at" block per step, and ends by
  opening the viewer. `pw next <id>` and the viewer hint share one function
  (`workspace/next_step.py`) that maps an asset's state to the next action.
- **Benchmark** (`src/pixelwright/bench/`): a run matrix (providers x chains x briefs x
  samples) with a cost estimate shown before anything is sent, detector scores from the
  check catalog, a Claude pairwise file Claude fills through MCP, a blind pairwise page in
  the viewer for the artist, Bradley-Terry ranking, and `report.html`.

<!-- -->

> **✎ Notes** · `PLAN › Architecture overview`
> _(your notes here — replace this line)_

### Data flow

```text
pw generate bg01 --provider comfyui --mode img2img --n 2
  -> style preset (style.yaml generation.comfyui) + asset sketch + palette
  -> GenRequest -> hash -> cache hit? -> GenResult (cost 0, logged)
                        -> miss: budget guard -> adapter.generate -> cache write -> ledger
  -> one version per image (stage draft, or experiment with --experiment),
     meta.yaml: provider, model, mode, request_hash, seed, cost_usd, cache_hit, licence
  -> envelope {"ok": true, "data": {"versions": ["v0007", "v0008"], "cost_usd": 0.0}}
```

<!-- -->

> **✎ Notes** · `PLAN › Data flow`
> _(your notes here — replace this line)_

### State changes

| Component | File | Change | Description |
|---|---|---|---|
| core | `pixelwright.toml` | UPDATE (optional tables) | `[providers.<name>]` (enabled, base_url, model, params), `[budget]` (`monthly_usd = 5.0`), `[defaults]` (provider per asset kind) |
| core | `cost.jsonl` | CREATE | One JSON line per call: time, provider, model, request_hash, n, cost_usd, cache_hit, asset, version |
| core | `.pixelwright/secrets.toml` | CREATE (by user) | `[keys] gemini = "..."`; git-ignored by `pw init`; env vars `PW_<PROVIDER>_KEY` win |
| core | `cache/<hash[:2]>/<hash>/` | CREATE | `request.json`, `response.json` (raw, keys stripped), `out_<n>.png` |
| core | `versions/vNNNN/meta.yaml` | UPDATE (extra fields) | `provider`, `model`, `mode`, `request_hash`, `seed`, `cost_usd`, `cache_hit`, `licence` |
| core | `style/style.yaml` | READ | `generation.<provider>`: preamble, negative, references, lora, strength, steps |
| bench | `benchmarks/<date>/` | CREATE | `matrix.yaml`, `runs/`, `scores.json`, `claude_pairs.jsonl`, `human_pairs.jsonl`, `report.html` |

All new fields are optional; a workspace from M2 loads unchanged.

<!-- -->

> **✎ Notes** · `PLAN › State changes`
> _(your notes here — replace this line)_

### Contracts

**`GenRequest`** (frozen dataclass): `mode` (`txt2img|img2img|edit|inpaint`), `prompt`,
`negative`, `init_image` (path or None), `mask` (path or None), `references` (paths),
`palette` (list of hex or None), `size` (w, h), `seed` (int or None), `n` (1-4),
`params` (dict). Hash = SHA-256 of canonical JSON with image paths replaced by their
SHA-256.

**Errors** (envelope from main spec §5): `provider_unavailable` (exit 5, e.g. ComfyUI not
running, with the fix in `message`), `provider_error` (exit 5, after retries),
`capability_missing` (exit 2, e.g. inpaint on Gemini), `missing_key` (exit 2, names the
env var and the secrets file), `budget_exceeded` (exit 6, with spent, limit and estimate).

**CLI** (all with `--json`):

| Command | Result `data` |
|---|---|
| `pw generate <id> --provider --mode [--prompt/--prompt-file] [--n] [--seed] [--experiment] [--dry-run]` | `versions`, `cost_usd`, `cache_hits`; `--dry-run`: `request_hash`, `estimate_usd` |
| `pw regen-region <id> --issue <n> --provider [--version]` | `version`, `pixels_changed`, `issue` |
| `pw cost [--month] [--by provider\|asset]` | `spent_usd`, `limit_usd`, `rows` |
| `pw doctor` | one row per check: Python, Aseprite, each provider (key present, reachable), budget, ComfyUI models |
| `pw next <id>` | `step`, `command`, `why` |
| `pw tour [--path] [--no-view]` | `workspace`, `steps` |
| `pw bench run --matrix <file> [--yes]`, `pw bench rank`, `pw bench report` | run ids, estimate; ranking; report path |

**MCP**: `generate`, `regen_region`, `cost_report`, `next_step`, `bench_*`, from the same
registry (M2 pattern).

<!-- -->

> **✎ Notes** · `PLAN › Contracts`
> _(your notes here — replace this line)_

### Technology choices

| Choice | Justification |
|---|---|
| stdlib `urllib` with an injectable transport | No new HTTP dependency; recorded-response tests are trivial |
| ComfyUI HTTP API (`/prompt`, `/history`, `/view`) with workflow JSON per preset in package data | Main spec contract; presets are editable files, not code |
| Bradley-Terry by MM iteration in numpy | ~20 lines; no stats dependency |
| Sample art drawn by code | D-M3-4: no third-party images; deterministic |

<!-- -->

> **✎ Notes** · `PLAN › Technology choices`
> _(your notes here — replace this line)_

### Out of scope

Style LoRA training, `animate` mode, scene preview and light zones, rigs, generation from the
viewer (D-M3-5), any provider without a licence note.

<!-- -->

> **✎ Notes** · `PLAN › Out of scope`
> _(your notes here — replace this line)_

## Implementation tasks

| T# | Description | Service | Size | Depends | Gate | Tests |
|----|-------------|---------|------|---------|------|-------|
| T34 | Providers | core | M | — | `make_check_exit_code == 0` | `test_same_request_twice_is_cache_hit_with_zero_cost` in `tests/core/test_providers.py` — the second call returns byte-identical images, cost 0, `cache_hit` true |
| T35 | Cost control | core, cli | M | T34 | `make_check_exit_code == 0` | `test_call_over_budget_is_refused_before_send` in `tests/core/test_budget.py` — exit 6 and the fake transport saw no request |
| T36 | Replay and sample | core, fixtures | S | T34 | `make_check_exit_code == 0` | `test_tour_sample_is_deterministic` in `tests/core/test_tour_sample.py` — two builds give identical sketch and painted PNG hashes |
| T37 | generate | cli, mcp | M | T35, T36 | `make_check_exit_code == 0` | `test_generate_n2_writes_two_versions_with_provider_meta` in `tests/cli/test_generate.py` — two versions, each `meta.yaml` with provider, request_hash, seed and cost |
| T38 | Next step | workspace, viewer | M | T37 | `e2e_failed == 0` | `test_next_step_covers_every_asset_state` in `tests/workspace/test_next_step.py` — every state maps to a command that exists in the registry |
| T39 | doctor | cli | S | T35 | `make_check_exit_code == 0` | `test_doctor_reports_missing_key_with_env_var_name` in `tests/cli/test_doctor.py` — a provider without key shows `PW_<NAME>_KEY` |
| T40 | tour | cli | M | T38 | `tour_seconds <= 60` | `test_tour_runs_whole_loop_offline` in `tests/cli/test_tour.py` — exits 0 with network blocked, ends with an exported asset and one approved version |
| T41 | Guide | docs, plugin | S | T40 | `make_check_exit_code == 0` | `test_plugin_skills_reference_existing_commands` in `tests/plugin/test_skills.py` — `first-run` names only commands in the registry |
| T42 | ComfyUI | core | L | T34 | `make_check_exit_code == 0` | `test_comfyui_img2img_replays_recorded_history` in `tests/core/test_comfyui.py` — recorded `/prompt` and `/history` responses give the recorded image |
| T43 | regen-region | cli, mcp | M | T37 | `pixels_changed_outside_mask == 0` | `test_regen_region_changes_nothing_outside_mask` in `tests/cli/test_regen_region.py` — byte compare outside the issue mask |
| T44 | Candidates | viewer | M | T37 | `e2e_failed == 0` | `test_compare_shows_candidates_of_one_generate` in `tests/viewer/e2e/test_candidates.py` — siblings with the same request_hash appear side by side |
| T45 | ComfyUI setup | docs, core | S | T42 | `make_check_exit_code == 0` | `test_presets_are_valid_workflow_json` in `tests/core/test_comfyui.py` — each preset loads and has the input nodes the adapter fills |
| T46 | Gemini | core | M | T34 | `make_check_exit_code == 0` | `test_gemini_img2img_sends_references_and_parses_image` in `tests/core/test_gemini.py` — request body matches the recorded shape; image decoded |
| T47 | Retro Diffusion | core | M | T34 | `make_check_exit_code == 0` | `test_retro_diffusion_sends_palette_and_strength` in `tests/core/test_retro_diffusion.py` — palette and strength in the body; image decoded |
| T48 | PixelLab | core | M | T34 | `make_check_exit_code == 0` | `test_pixellab_inpaint_sends_mask` in `tests/core/test_pixellab.py` — mask in the body; image decoded |
| T49 | GPT Image | core | M | T34 | `make_check_exit_code == 0` | `test_gpt_image_edit_sends_mask_and_parses_b64` in `tests/core/test_gpt_image.py` — edit request with mask; image decoded |
| T50 | Bench run | bench, cli | L | T37 | `estimate_shown_before_send == 1` | `test_bench_run_refuses_without_yes_and_shows_estimate` in `tests/bench/test_run.py` — no request before `--yes`; estimate printed |
| T51 | Ranking | bench, viewer | L | T50 | `e2e_failed == 0` | `test_bradley_terry_recovers_known_order` in `tests/bench/test_rank.py` — synthetic pairs rank in the true order; `test_blind_page_hides_provider_names` in `tests/viewer/e2e/test_blind.py` |

<!-- -->

> **✎ Notes** · `PLAN › Implementation tasks`
> _(your notes here — replace this line)_

### Task details

- **T34 Framework**: protocol, dataclasses, registry, hasher, cache, retry/backoff, transport
  injection, errors; a `fake` provider for tests only.
- **T35 Cost control**: `[budget]` and secrets loading, guard before every non-cached call
  (estimate + spent this month > limit → exit 6), `cost.jsonl`, `pw cost`, `.gitignore`
  entries for `cache/`, `.pixelwright/secrets.toml`.
- **T36 Replay and sample**: `replay` serves images from a folder keyed by request hash or
  in order; `fixtures/tour.py` draws a small sketch (lines) and a "painted" version (soft
  gradients and noise) at 4x of a 160x90 canvas, so snap and quantize have work to do.
- **T37 generate**: modes txt2img/img2img/edit/inpaint per capability, style preset merge
  (preamble + prompt, references, palette as input or swatch image), `--n` candidates,
  `--experiment` stage, `--dry-run`; MCP tool.
- **T38 Next step**: states (no source, sketch only, raw generated, snapped, quantized,
  cleaned, checks failing, open issues, ready to approve, approved, exported) → command and
  one-line why; `pw next`; the viewer shows it in the empty side panel and status bar.
- **T39 doctor**: table output plus `--json`; each failing row says how to fix it.
- **T40 tour**: steps with a "what happened / why / look at" block each; `--path` keeps the
  workspace; opens `pw view` at the end unless `--no-view`.
- **T41 Guide**: `docs/guide/how-it-works.md` (one drawspec diagram of the loop, glossary,
  "your first real asset"); README and `pw --help` link it; plugin skill `first-run`.
- **T42 ComfyUI**: queue a workflow, poll history, fetch images; txt2img, img2img, inpaint;
  clear `provider_unavailable` when the server is down; recorded responses in tests.
- **T43 regen-region**: build an inpaint request from the issue mask (box or PNG), paste
  the result only inside the mask, resolve the issue with the new version.
- **T44 Candidates**: Compare offers siblings sharing a request hash; pick one, reject the rest.
- **T45 Setup**: install guide (ComfyUI, models, a pixel-art LoRA with a licence note),
  presets for Flux and SDXL, and `status/m3/local-comfyui-test-prompt.md` for the owner's
  local session.
- **T46-T49 Paid adapters**: each from the provider's current API docs at implementation
  time; capability flags, price per image, licence note, recorded responses with keys
  stripped. Real calls only in the owner's local session.
- **T50 Bench run**: `matrix.yaml` (main spec: 3 generators x 2 chains x 3 briefs x 3
  samples), estimate, `--yes` to spend, resumable, detector scores per output.
- **T51 Ranking**: Claude pairwise through MCP (`bench_pairs_next`, `bench_pair_record`),
  blind pairwise page in the viewer, Bradley-Terry, `report.html`, `pw bench apply` writes
  `[defaults]`.

**Status legend**: ☐ not started · ◐ in progress · ☑ merged

**Merge order**: T34; T35, T36, T42, T46-T49 (parallel); T37, T39, T45; T38, T43, T44, T50; T40, T51; T41
**Branch pattern**: `pw-T<N>-description` from the default branch

<!-- -->

> **✎ Notes** · `PLAN › Task details`
> _(your notes here — replace this line)_

### Dependency graph

Generated from the **Depends** column — never drawn by hand.

```drawspec
{"version": 1, "kind": "flow", "title": "Task dependencies — phases",
 "nodes": [
  {"id": "P1", "text": "Phase 1\nT34, T35, T36, T42, T46, T47, T48,…"},
  {"id": "P2", "text": "Phase 2\nT39, T45, T38, T43, T44, T50, T40,…"}
 ],
 "edges": [
  {"from": "P1", "to": "P2"}
 ]}
```

**Phase 1** — T34, T35, T36, T42, T46, T47, T48, T49, T37

```drawspec
{"version": 1, "kind": "flow", "title": "Task dependencies — phase 1",
 "nodes": [
  {"id": "T34", "text": "T34\nProviders"},
  {"id": "T35", "text": "T35\nCost control"},
  {"id": "T36", "text": "T36\nReplay and sample"},
  {"id": "T42", "text": "T42\nComfyUI"},
  {"id": "T46", "text": "T46\nGemini"},
  {"id": "T47", "text": "T47\nRetro Diffusion"},
  {"id": "T48", "text": "T48\nPixelLab"},
  {"id": "T49", "text": "T49\nGPT Image"},
  {"id": "T37", "text": "T37\ngenerate"}
 ],
 "edges": [
  {"from": "T34", "to": "T35"},
  {"from": "T34", "to": "T36"},
  {"from": "T35", "to": "T37"},
  {"from": "T36", "to": "T37"},
  {"from": "T34", "to": "T42"},
  {"from": "T34", "to": "T46"},
  {"from": "T34", "to": "T47"},
  {"from": "T34", "to": "T48"},
  {"from": "T34", "to": "T49"}
 ]}
```

**Phase 2** — T39, T45, T38, T43, T44, T50, T40, T51, T41 (with T35, T37, T42 from earlier phases)

```drawspec
{"version": 1, "kind": "flow", "title": "Task dependencies — phase 2",
 "nodes": [
  {"id": "T35", "text": "T35\nphase 1"},
  {"id": "T37", "text": "T37\nphase 1"},
  {"id": "T42", "text": "T42\nphase 1"},
  {"id": "T39", "text": "T39\ndoctor"},
  {"id": "T45", "text": "T45\nComfyUI setup"},
  {"id": "T38", "text": "T38\nNext step"},
  {"id": "T43", "text": "T43\nregen-region"},
  {"id": "T44", "text": "T44\nCandidates"},
  {"id": "T50", "text": "T50\nBench run"},
  {"id": "T40", "text": "T40\ntour"},
  {"id": "T51", "text": "T51\nRanking"},
  {"id": "T41", "text": "T41\nGuide"}
 ],
 "edges": [
  {"from": "T37", "to": "T38"},
  {"from": "T35", "to": "T39"},
  {"from": "T38", "to": "T40"},
  {"from": "T40", "to": "T41"},
  {"from": "T37", "to": "T43"},
  {"from": "T37", "to": "T44"},
  {"from": "T42", "to": "T45"},
  {"from": "T37", "to": "T50"},
  {"from": "T50", "to": "T51"}
 ]}
```

<!-- -->

> **✎ Notes** · `PLAN › Dependency graph`
> _(your notes here — replace this line)_

## Risks

| Risk | Likelihood | Impact | Mitigation | Rollback |
|---|---|---|---|---|
| A paid API changed shape since the research | High | Med | Each adapter is written from current docs; recorded responses; the owner runs one real call per adapter locally before the benchmark | Disable the adapter in `pixelwright.toml` |
| Key leaks into git, cache or logs | Low | High | Keys only in env or git-ignored secrets file; recorder strips auth headers and query keys; gitleaks in CI | Rotate the key |
| Unexpected spend | Low | Med | Budget guard before every call, `--dry-run`, bench refuses without `--yes` and shows the estimate | Hard stop at the monthly limit |
| ComfyUI setup is hard on the owner's machine | Med | Med | `pw doctor` checks the server and models; setup guide; replay keeps everything else usable | Use a paid provider meanwhile |
| The tour still does not make the loop clear | Med | High | Owner runs it before M3b; each step's text is reviewed; feedback round planned | Rewrite step texts; no code risk |
| Inpaint result bleeds outside the mask | Med | Med | Gate: pixels changed outside mask = 0; paste only inside the mask | History keeps the parent |

<!-- -->

> **✎ Notes** · `PLAN › Risks`
> _(your notes here — replace this line)_

## Evidence log

| T# | Gate | Measured | Command | SHA | Env | Date |
|----|------|----------|---------|-----|-----|------|

<!-- -->

> **✎ Notes** · `PLAN › Evidence log`
> _(your notes here — replace this line)_

## Sign-off

- [ ] Design reviewed by the owner
- [ ] Contracts agreed (state changes and CLI table above)
- [ ] Ready for execution

<!-- -->

> **✎ Notes** · `PLAN › Sign-off`
> _(your notes here — replace this line)_

