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

pixelwright ships three presets. Put the files in the ComfyUI folders named below. Each
model has its own licence: read the model card before shipping game art made with it, and
note the licence beside the preset in `pixelwright.toml`.

| Preset | Files | Folder | Licence to check |
|---|---|---|---|
| `sdxl` (default) | `sd_xl_base_1.0.safetensors` | `models/checkpoints/` | CreativeML Open RAIL++-M (commercial use allowed with use restrictions) |
| | a pixel-art LoRA, e.g. `pixel-art-xl.safetensors` | `models/loras/` | the LoRA's own card |
| `sdxl-controlnet` | the `sdxl` files, plus `controlnet-canny-sdxl-1.0.safetensors` (diffusers) | `models/controlnet/` | openrail++ |
| `flux-schnell` | `flux1-schnell.safetensors` | `models/unet/` | Apache-2.0 |
| | `t5xxl_fp8_e4m3fn.safetensors`, `clip_l.safetensors` | `models/clip/` | Apache-2.0 / MIT |
| | `ae.safetensors` | `models/vae/` | Apache-2.0 |

FLUX.1 [dev] weights are under a non-commercial licence; the `flux-schnell` preset avoids them.

File names other than these? Set them in `pixelwright.toml` (`[presets.comfyui]`; a
`style/style.yaml` is not read):

```toml
[presets.comfyui]
preamble = "pixel art, 1990s point-and-click adventure background"
negative = "blurry, photo, 3d render, text"
scale = 4                     # paint at 4x the canvas; snap brings it back

[presets.comfyui.params]
preset = "sdxl"               # or sdxl-controlnet, flux-schnell
ckpt = "my_sdxl.safetensors"
lora = "my_pixel_lora.safetensors"
lora_strength = 0.7           # 0.6-1.0 usable on a 4060; 0.7 the cleanest
denoise = 0.75                # img2img: how far from the sketch (0 keeps it, 1 ignores it)
steps = 30
```

**Sizes.** SDXL and Flux compose at about 1024 px: ask `--size 1024x576` for 16:9
(below 768 px on the long side the presets refuse; at 640x360 SDXL breaks the scene into
tiles). img2img scales the init image to that size first, so a 320x180 sketch works.
Measured on an RTX 4060 Laptop (8 GB): txt2img 1024x576 about 70 s and 7.1 GB VRAM;
img2img about 26 s and 6.5 GB.

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

## Sketch or layout to scene (ControlNet)

The `sdxl-controlnet` preset keeps the lines of an image and paints it anew: a rough
sketch, or a scene composed with `pw scene compose` (the camera and the scale are then
right before the model starts). The init image goes through ComfyUI's built-in `Canny`
node into ControlNet; nothing of its colour is kept.

```bash
pw add scenes/crypt --from export/scenes/crypt.png
pw generate scenes/crypt --provider comfyui --mode img2img --size 1024x576 \
  --prompt "a stone crypt with a sarcophagus, torchlight"
```

```toml
[presets.comfyui.params]
preset = "sdxl-controlnet"
control_strength = 0.7   # how firmly the lines hold (0.5 looser, 0.9 traced)
control_end = 0.8        # let the last 20 % of the steps add detail freely
```

- Ask for 1024x576 (SDXL's native area, 16:9); `pw normalize` brings it to 320x180.
  Below about 768 px SDXL composition falls apart (task #119).
- VRAM: SDXL + ControlNet fits in 8 GB at 1024x576 with ComfyUI's defaults.
- Quality on real scenes is still to be judged on the GPU (task #201).
