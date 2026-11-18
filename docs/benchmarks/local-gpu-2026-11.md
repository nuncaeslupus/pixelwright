# Local route on a consumer GPU (2026-11)

Task #201. ComfyUI on an RTX 4060 Laptop (8 GB VRAM, 15 GB RAM), presets as of #206.
Everything fits in 8 GB without low-VRAM mode; system RAM is the real limit.

| Preset | Use | Size | Time | Result |
|---|---|---|---|---|
| `flux-schnell` txt2img | scene from a prompt | 1024x576, 4 steps | ~24 s | best: a cabin at sunset, a dark crypt, both strong without a LoRA; does not collapse at 640x360 |
| `sdxl` + LoRA 0.7 txt2img | scene from a prompt | 1024x576 | ~70 s | usable, below Flux |
| `sdxl-controlnet`, strength 0.9 | layout to scene | 1024x576 | ~90 s | keeps the layout: door, two torches, sarcophagus and walls in place |
| `sdxl-controlnet`, strength 0.7 | layout to scene | 1024x576 | ~90 s | the LoRA turns the crypt into outdoor ruins |
| `sdxl-controlnet`, strength 0.5 | layout to scene | 1024x576 | ~90 s | layout lost |
| `flux-schnell` img2img, 4 steps | retouch | 1024x576 | | denoise 0.85 is pixel-identical to txt2img; 0.7 nearly copies the sketch |
| `flux-schnell` img2img, 8 steps | retouch | 1024x576 | | still copies the sketch up to 0.85 |

## Findings

- Canny passes only edges: colour and light (a sunset) must come from the prompt.
- Interior scenes need "interior ..., no sky" in the prompt with ControlNet.
- Flux fp8: `flux1-schnell-fp8-e4m3fn.safetensors` set as `unet` in the params; `ae.safetensors`
  from the Comfy-Org mirror (the original repository is gated).
- Changed after this run: `sdxl-controlnet` defaults to `control_strength = 0.9`.

## Not done

- No side-by-side judgement against Retro Diffusion yet: the owner judges the contact
  sheets. No sprite was tried on the local route.
