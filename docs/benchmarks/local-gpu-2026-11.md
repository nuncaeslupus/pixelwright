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

## Round 2-3: making Flux better (18 + more runs, 1280x720)

| Change | Effect |
|---|---|
| Describe the layout (what is where) instead of naming the scene | biggest gain: the layout holds on all 3 seeds |
| Several seeds, pick one | all usable, ~20 s each |
| Style words ("16-bit, VGA, dithering") | little change |
| Colour names in the prompt | almost none |
| Forced palette at normalize | worse: banded sky, dull colours |
| 8 or 12 steps instead of 4 | same or flatter; 12 steps drops the fake signature but adds odd objects |
| Second pass at higher resolution | invisible after reducing to 320x180 |
| Pixel-art LoRA (MIT, trained on FLUX.1 [dev]) at 0.8 | more contrast, cleaner outlines, same layout and time (~14 s) |
| A second "pixel background" LoRA | everything turns pastel; dropped |

Recipe: detailed description + LoRA 0.8 + 4 steps, 4 seeds per scene, about a minute.
Bugs found and fixed: `pw normalize` guessed a 5 px grid on a 1280x720 image (256x144);
an exact multiple of the canvas now sets the grid. Next model to try: an undistilled
Flux (real negative prompt), about 9 GB.

## Rounds 4-10: Chroma and the VGA look

| Round | Change | Result |
|---|---|---|
| 4 | Chroma1-HD fp8, 26 steps | the best local model: more atmosphere, follows the description, no fake signature; ~90 s |
| 5 | VGA preamble (readable clusters, smooth ramps, calm areas) + anti-noise negative | readable pixels; a "very simple" prompt is flat and pale |
| 6 | contrast and atmosphere words; cfg 4.5 | more drama; some seeds draw a tiny scene on a flat background |
| 7 | `colors = 256` instead of pw's 24 | the flat blocks were pw's; stone edges and grass shades come back |
| 7 | material lines (dark joint, lit edge) | every stone reads, near and far from the light |
| 7-9 | vignette and torch flicker after generation, in the image's colours | work; in the prompt they break the scene |
| 8-9 | sharpen + 48-64 colours | pixels pop but detail and contrast suffer; the owner prefers 128-256 |
| 10 | 128 colours per scene | nearly the same as 256 (scenes use ~120) |
| 10 | one palette fitted to two scenes at once | grass takes the colours; the crypt loses its flame oranges |
| 10 | per-scene union (58 own + 4 brightest + 2 darkest each) | 124 colours, both scenes look as with their own |

Built from this: the `chroma` preset, 128 colours for painted inputs, `pw palette discover
--per-image`, and `[[light]]` / `vignette` in scenes. Guide: `docs/guide/painted-scenes.md`.

## Not done

- No side-by-side judgement against Retro Diffusion yet: the owner judges the contact
  sheets. No sprite was tried on the local route.
