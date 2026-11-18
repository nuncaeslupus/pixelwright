# Painted scenes: the 1990s VGA adventure look on a local GPU

What we learned making point-and-click backgrounds (a torch-lit crypt, a cottage on a hill)
with ComfyUI on an RTX 4060 Laptop with 8 GB of VRAM, over ten rounds of tests. The target
was the 256-colour VGA look: pixels you can read, detail and atmosphere, no photographic
noise, no outline on every stone, and no big flat blocks of one colour. Measurements:
[local GPU benchmark](../benchmarks/local-gpu-2026-11.md). Model setup: [ComfyUI](comfyui.md).

## The recipe

| Step | Setting | Why |
|---|---|---|
| Model | preset `chroma`: Chroma1-HD fp8 (`Chroma1-HD-fp8mixed-final.safetensors`, Apache-2.0, 9.2 GB) in `models/unet/`, `t5xxl_fp8_e4m3fn` in `models/clip/`, `ae` in `models/vae/` | the best local model tested: light, atmosphere, follows the description, obeys the negative prompt |
| Sampling | 26 steps, cfg 3.8 (4.5 for more drama), euler / beta | 16 steps is grainier; more steps buy nothing |
| Size | `--size 1280x720`, the 320x180 canvas x 4 | normalize takes 4 px per pixel |
| Seeds | 3 per scene, pick one | ~95 s each; some seeds draw a small scene floating on a flat background |
| LoRA | none | pixel-art LoRAs flatten or darken Chroma |
| Colours | painted inputs keep 128 colours (the default since this guide) | fewer melt stone edges, grass and sky into flat blocks |
| Palette | one game palette from the approved scenes (below) | every scene shares the same colours |
| Post | vignette and flickering lights in `pw scene` | both after generation, never in the prompt |

About 5 minutes per scene with 3 seeds. For fast drafts, `flux-schnell` with a pixel-art
LoRA takes ~14 s, but it outlines every stone whatever the prompt says.

```toml
# pixelwright.toml
[presets.comfyui]
preamble = "..."   # the style preamble below
negative = "..."   # the negative prompt below

[presets.comfyui.params]
preset = "chroma"
```

## The prompt has four parts

1. **Style preamble**, the same for every scene:

   > classic 1990s 256-colour VGA point-and-click adventure game background, richly detailed
   > hand-drawn pixel art with clean readable pixel clusters. Moody, atmospheric lighting with
   > strong contrast between bright light sources and deep shadows, rich colour ramps of five
   > or six shades per material. Every surface carries deliberate pixel-cluster texture; no
   > large flat single-colour areas. No noise, no grain, no photographic texture, no
   > single-pixel speckles. No text, no signature, no watermark.

2. **The scene, saying what goes where.** This is the biggest lever: name the camera, what is
   in the back, the centre and the foreground, and where the light comes from. Naming the
   scene ("a crypt") lets the model compose it; describing it makes every seed keep the layout.

   > Interior of an underground stone crypt seen from the front. In the back wall, an arched
   > wooden door with a wall torch on each side throwing warm orange light. In the centre of
   > the floor, in front of the door, a long stone sarcophagus with a carved lid. The corners
   > fall into deep blue shadow. Cracked flagstone floor, cobwebs, a few bones and an old urn.

3. **Material lines** for the surfaces that would otherwise go flat or noisy:
   - stone: "Every wall stone and floor slab is a distinct block with a dark mortar gap and a
     lighter lit edge, clearly readable both near the torches and far away in the dark."
   - grass: "The grass is drawn as clearly readable clumps and blades in many shades of
     green, lit consistently by the low sun from one side, with a few wildflowers and rocks."
   - wood: "The broken fence has clear posts and rails, each with a lit side and a shadow side."

4. **Negative prompt** (Chroma uses real CFG, so this works):

   > This is a noisy, grainy image full of single-pixel speckles and photographic
   > micro-texture, with smooth gradients, anti-aliasing and blur. Large flat areas of a
   > single colour, washed-out, low-contrast colours. It has text, a watermark and a signature.

## Colours: 128 is the sweet spot

- With 24 colours (pw's old default for a painting) stone edges, grass shades and the sky
  melt into flat blocks. That was pw, not the model.
- 128 colours looks nearly the same as 256: a scene really uses ~120. On a normal screen,
  enlarged, the pixels already show.
- 48 colours after a sharpen makes every pixel pop but loses information and contrast;
  32 colours turns the torch glow into blobs.

## One palette for the whole game

All scenes of a game should share one palette. A palette fitted to all scenes at once is
biased by area: the grass takes most colours and the crypt loses its flame oranges. What
works is a union of each scene's own colours:

```bash
pw palette discover --asset scenes/crypt scenes/cottage --per-image 58 --name game --swatch
```

Each scene brings its own 58 colours, plus 4 for its brightest 0.3 % (flame cores, glints)
and 2 for its darkest 1 % (true blacks); near-equal colours merge. Two scenes gave 124
colours; each looked almost the same as with its own 128. Rebuild it when a scene is
approved, then normalize the earlier scenes again with `palette = "game"`.

The character palettes made earlier did not fit scenes: no fire oranges (green flames, grey
crypt), or violet grass. Build scene palettes from scenes.

## Light, vignette and animation

`pw scene` adds both after composing, in the scene's own colours (no new colour appears):

```toml
[scene]
vignette = 0.12            # darken the corners by this much lightness

[[light]]                  # a torch: its surroundings brighten and dim on their own rhythm
at = [70, 72]
radius = 120               # px
strength = 0.15            # lightness added at the centre at full flame

[[flame]]                  # the painted flame itself, animated in place
box = [67, 62, 10, 18]     # x, y, w, h around the flame only
```

`pw scene compose <name> --gif` writes the 8-frame loop. A flame box animates the painted
flame in place: its own colours flow upwards by heat (palette cycling) and its coolest
tips come and go, showing the pixel beside them. Keep the box tight: lit wall inside it
would flicker as fire. A light changes each pixel to the
scene colour of the same hue nearest to its new lightness: warm walls stay warm, the dark
void beside them stays dark, and the flame pixels keep their colours. Asking for a vignette
in the prompt does not work: Chroma draws a cut-out diorama on black, or a tiny scene.

Animation, from cheapest to hardest (always in the game palette):

1. **Light that moves**: torches, a fireplace glow, a lit window, lightning (one bright
   frame), water shimmer. Done, as above.
2. **Small looping effects**: the flame itself (`[[flame]]`, done), and smoke, water or
   flags as small strips of frames on their own layer (`states` with `frames` in the
   scene).
3. **Characters**: a reference character, then keyframes per action (walk: contact, down,
   passing, up) from a pose guide (ControlNet OpenPose locally, or Retro Diffusion's
   animation styles), all at the same size, foot pivot and palette. The long road; see
   task #208.

## What did not work

| Tried | Result |
|---|---|
| SDXL + pixel-art LoRA | usable, less mood; collapses below ~768 px |
| Flux schnell (+ pixel LoRA) | fast drafts; outlines every stone, paints a fake signature |
| More steps on Flux schnell | it is distilled: flatter, not better |
| A "very simple VGA" prompt (2-3 flat tones) | flat, pale, no mood |
| "vignette" or "edge to edge" in the prompt | a diorama on black, or a tiny floating scene |
| Style words ("16-bit, VGA, dithering") or colour names alone | little change |
| A forced palette at generation, contrast boosts, 4x4 majority downscale | banded sky; flames lost |
