# Local generation with ComfyUI

pixelwright's free route paints on your own NVIDIA GPU through [ComfyUI](https://github.com/comfyanonymous/ComfyUI).
pixelwright never runs ComfyUI itself: you start it, and `pw generate --provider comfyui`
sends it a workflow over its local HTTP API (`http://127.0.0.1:8188`).

## 1. Install ComfyUI (Ubuntu, NVIDIA)

```bash
git clone https://github.com/comfyanonymous/ComfyUI ~/ComfyUI
cd ~/ComfyUI
python3 -m venv .venv && . .venv/bin/activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124  # match your CUDA
pip install -r requirements.txt
python main.py            # leave it running; open http://127.0.0.1:8188 to check
```

Check from your workspace: `pw doctor` shows `ok comfyui` with your GPU name.

## 2. Models

pixelwright ships two presets. Put the files in the ComfyUI folders named below. Each
model has its own licence: read the model card before shipping game art made with it, and
note the licence in `style/style.yaml` (`presets.comfyui.licence`).

| Preset | Files | Folder | Licence to check |
|---|---|---|---|
| `sdxl` (default) | `sd_xl_base_1.0.safetensors` | `models/checkpoints/` | CreativeML Open RAIL++-M (commercial use allowed with use restrictions) |
| | a pixel-art LoRA, e.g. `pixel-art-xl.safetensors` | `models/loras/` | the LoRA's own card |
| `flux-schnell` | `flux1-schnell.safetensors` | `models/unet/` | Apache-2.0 |
| | `t5xxl_fp8_e4m3fn.safetensors`, `clip_l.safetensors` | `models/clip/` | Apache-2.0 / MIT |
| | `ae.safetensors` | `models/vae/` | Apache-2.0 |

FLUX.1 [dev] weights are under a non-commercial licence; the `flux-schnell` preset avoids them.

File names other than these? Set them per preset in `style/style.yaml`:

```yaml
presets:
  comfyui:
    preamble: "pixel art, 1990s point-and-click adventure background,"
    negative: "blurry, photo, 3d render, text"
    scale: 4                 # paint at 4x the canvas; snap brings it back
    params:
      preset: sdxl           # or flux-schnell
      ckpt: my_sdxl.safetensors
      lora: my_pixel_lora.safetensors
      lora_strength: 0.9
      denoise: 0.6           # img2img: how far from the sketch (0 keeps it, 1 ignores it)
      steps: 30
```

## 3. Project settings

```toml
# pixelwright.toml
[providers.comfyui]
base_url = "http://127.0.0.1:8188"   # another machine on your network works too

[defaults]
background = "comfyui"               # provider per asset kind
```

## 4. First run

```bash
pw add scenes/hill --from my-sketch.png --kind background
pw generate scenes/hill --provider comfyui --init input --prompt "a house on a hill at dusk" --n 2 --seed 1
```

Each result is normalised and checked like any other input. The same request twice is free and instant: it comes from `cache/`.

## When it fails

| Message | Fix |
|---|---|
| `ComfyUI is not answering` | start `python main.py`, or fix `base_url` |
| `prompt ... failed` with a missing file | the model name in the preset is not in the ComfyUI folders; set `ckpt` / `lora` / `unet` |
| out of memory | lower `--size`, use `--n 1`, or the fp8 T5 file for Flux |
