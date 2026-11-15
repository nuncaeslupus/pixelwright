# Local test prompt: generation on the owner's machine (M3)

Paste this into a Claude Code session on your own computer, in your pixelwright clone. It
runs the parts the cloud cannot: your GPU, ComfyUI and real calls to the paid APIs.
Paid calls are capped by the script: at most 1 image per provider, about 0.40 USD in total.

---

You are testing pixelwright's M3 generation on this machine. Work in a scratch workspace
under /tmp, never in the repo. Do not commit anything. Report results at the end as a short
table: step, result (ok / fail), and the exact error message on failure.

1. `git pull` on main, then `uv sync`. Run `uv run pw --help` and check `generate`,
   `cost` and `doctor` are listed.
2. Create `/tmp/pw-m3` with `uv run pw init /tmp/pw-m3`, then `cd /tmp/pw-m3`.
3. Run `uv run pw doctor` and paste its output.
4. Make the tour sample and an asset:
   `uv run python -c "from pixelwright.fixtures import tour; from pixelwright.io.png import write_png; from pathlib import Path; write_png(Path('sketch.png'), tour.sketch())"`
   then `uv run pw new hill --kind background --canvas 160x90` and
   `uv run pw attach hill sketch.png --as sketch`.
5. ComfyUI (skip if `pw doctor` says it is not running and the owner does not want to start
   it; see docs/guide/comfyui.md): run
   `uv run pw generate hill --provider comfyui --prompt "a house on a hill at dusk" --seed 1`
   then the same command again (must say `cache_hit: true`). Then
   `uv run pw snap hill && uv run pw quantize hill && uv run pw clean hill && uv run pw check hill`.
   Repeat the generate with `--size 640x360 --mode txt2img` and with
   `[providers.comfyui]`-free defaults for the `flux-schnell` preset if those models exist
   (`style/style.yaml` → `presets.comfyui.params.preset: flux-schnell`).
6. Paid providers, only those whose key the owner has set (`PW_GEMINI_KEY`,
   `PW_RETRO_DIFFUSION_KEY`, `PW_PIXELLAB_KEY`, `PW_GPT_IMAGE_KEY`, or
   `.pixelwright/secrets.toml`). For each one, first
   `uv run pw generate hill --provider <name> --prompt "a house on a hill at dusk" --dry-run`
   (shows the estimate), then the same without `--dry-run`, `--n 1`, `--seed 1`. For
   `pixellab` and `retro-diffusion` add `--size 160x90`. For `gemini` and `gpt-image` the
   default size is fine. If a call fails with HTTP 400/422, paste the full error `details`:
   the adapter's field names need fixing.
7. `uv run pw cost --by provider` and paste it.
8. `uv run pw view` and look at the versions; say in one line per provider how close the raw
   image looks to pixel art and to the sketch.
9. Delete `/tmp/pw-m3` unless the owner wants to keep it.
