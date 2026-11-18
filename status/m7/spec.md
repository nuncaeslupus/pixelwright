# M7: scenes built in layers, and a local route

**Date**: 2026-11-18
**Status**: scope agreed with the owner (2026-11-17 Retro Diffusion review); tasks asked for on 2026-11-18
**Evidence**: `docs/benchmarks/retro-diffusion-2026-11.md`

## Problem

One model call cannot draw a good 320x180 adventure scene with the right objects at the
right scale. Retro Diffusion `rd_pro` draws the best detail but stops at 256 px;
`rd_plus` reaches 320x180 (384 wide) but is simpler. Building the scene in layers worked
(empty room from `plus`, props and characters from `pro`), but the pieces did not agree:
a 3/4 tomb on a frontal room, no shadow under it, and no rule for how tall a person is at
each depth. Paid calls also cost money on every try; the owner has an NVIDIA GPU.

## Decisions

- **D-M7-1 Scene file.** A scene is `scenes/<name>.toml` in the project: viewport (default
  the project canvas, 320x180), world width (wider for scrolling), horizon line, camera
  (`frontal`, `three-quarter`, `side`), a scale reference, and a list of layers that name
  assets. Plain TOML, readable without pixelwright.
- **D-M7-2 Scale from the ground plane.** One reference gives every depth: a person whose
  feet are at row `y` is `h(y) = h_ref * (y - horizon) / (y_ref - horizon)` pixels tall.
  The reference is a person (`y`, `height`) or a door (`y`, `height`, times
  `person_to_door`, default 0.85).
- **D-M7-3 Layers are placed by their base.** A layer's `at = [x, y]` is the bottom centre
  (where it touches the floor). Layers draw in order of base row; `z` overrides (a pillar
  in front). Nothing is resampled: pixel art cannot be scaled.
- **D-M7-4 Contact shadows at compose time.** An ellipse under each grounded layer,
  flattened by depth, darkens the floor using colours already in the background, so the
  palette does not grow.
- **D-M7-5 Character sizes.** A character lists one asset per size. Compose picks the size
  nearest to `h(y)` and warns past 15 %. `pw scene sizes` suggests the heights to draw
  (steps of 0.75 across the walkable band), each a simplified redraw that fills its frame.
- **D-M7-6 Same camera for props.** `pw generate --scene <name> --at <y>` adds the scene's
  camera, horizon and the target size to the prompt.
- **D-M7-7 Scrolling in two steps.** A wide scene has several background tiles placed by x.
  Overlapping tiles are joined along the lowest-difference seam, never blended (no new
  colours).
- **D-M7-8 Object states and animation.** A layer has named states (`closed`, `open`), each
  an asset; an animated state is a horizontal strip of frames. Compose takes `--state`
  and can write the whole scene as an animated GIF.
- **D-M7-9 Local route.** SDXL or Flux with a pixel-art LoRA in ComfyUI on the owner's GPU,
  guided by ControlNet from a sketch (or a composed layout), then `pw normalize`. Free per
  image; quality is judged by the owner against the Retro Diffusion results.

## Out of scope

Engine export of the layout beyond the JSON written next to the image; walk boxes and
hotspots; parallax.
