# Retro Diffusion: first real test (2026-11-17)

First real run against the Retro Diffusion (RD) API, compared with the Gemini results
from the same week. About $4 spent on ~30 images. Not a benchmark run: a first contact to
learn what the provider can do for an adventure game at 320x180.

## Account and API

- The free trial credits work only in the web app. Through the API, every call failed with
  `insufficient_balance` until prepaid balance was added.
- The key is read from `PW_RETRO_DIFFUSION_KEY`, which matches the adapter's naming.
- A cloud session needs `api.retrodiffusion.ai` on its network allowlist.
- The valid styles are listed at `GET /v2/styles/selector`. The README of
  `Retro-Diffusion/api-examples` lists sizes and prices per style.

## Models and limits

| Style | Size | Price | Use |
|---|---|---|---|
| `rd_pro__default`, `rd_pro__fantasy` | 12-256 px | $0.18 | Best detail. Sprites and props. Scenes only up to 256x144 |
| `rd_plus__environment` | 64-384 px | ~$0.06 at 320x180 | Scenes at 320x180. Vivid, but simpler and follows the prompt less |
| `rd_core__default` | ? | $0.10 | Flat and washed out in our test |
| `rd_tile__scene_object` | 64-384 px | $0.06 | Props. Weaker than pro |
| `rd_advanced_animation__custom_action` | 32-256 px | $0.25 | 8-frame GIF from one image and a prompt |

- The inpainting tool is also limited to 256x256. A pro scene cannot be outpainted to
  320x180 in one call.
- Output is native pixel art (one pixel per cell). Normalise must keep it as drawn (fixed in
  this PR: a 320x180 input was snapped to a false 34x18 grid).

## Findings

- **Sprites.** `rd_pro` at 48x80 with `remove_bg` gives clean sprites with outlines, as good
  as Gemini or better. `remove_bg` failed on 2 of 3 innkeepers (a flat blue box remained).
- **Palette.** `input_palette` (a 1-row PNG) constrains colours during generation.
  - The 62-colour adventure ramps limited fire, floors and wood. 110 colours (`--steps 9`)
    gave smoother gradients.
  - Mean saturation of the tavern: Gemini 36-37, RD without palette 69-85, RD with ramps
    42-63.
  - Hex codes in the prompt add nothing (removed from prompts in this PR).
- **Scenes at 320x180.**
  - "Pro → plus" (pro at 256x144, enlarged, redrawn by plus at strength 0.4) was rejected:
    odd objects, wrong scale.
  - Building scenes in layers works: plus draws an empty room at 320x180, pro draws each
    prop (128x64 sarcophagus with `remove_bg`), and they are composited. It still needs:
    - a scale reference per scene (door height → person height);
    - props asked with the background's camera and horizon (the 3/4 tomb on a frontal
      room looked wrong);
    - contact shadows.
- **Animation.**
  - `custom_action` on the 48x80 innkeeper ("drinks, then slams the tankard on a table")
    worked. It needs a wider frame (96x80) so the arm and table fit. Props can pop in
    mid-animation. Expect hand touch-ups.
  - A tomb "opening" lifted the lid and closed it again in a loop. Ask for an animation that
    ends open, or draw the open state as a second object.
- **Character sizes for depth.** Pixel art cannot be downscaled. Each size is a simplified
  redraw.
  - `rd_pro` with the 48x80 knight as `reference_images` gave a good 36x60.
  - At 24x40 the figure came out much smaller than the frame and noisy.
  - Ask for the figure to fill the frame, and check the height of each size.

## Open ideas (not planned)

- Scene-by-layers flow in `pw`: background + props + characters, with a scale reference,
  camera and horizon, contact shadows and depth sizes per character.
- Scrolling scenes in two steps (640x180): two backgrounds that join, composed with props.
  `rd_plus` reaches 384x180 in one image.
