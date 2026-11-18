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

## Layered crypt with `pw scene` (2026-11-18, $0.42)

The empty crypt from round 3 as background, with the tomb asked through `pw scene prompt`
(frontal camera, eye level above the lid, 40 px next to an 81 px person).

- **Camera match works.** `rd_pro__fantasy` 128x64 drew the open tomb straight from the
  front, lid leaning on its side, in the room's own colours (`input_palette` = the
  background's 75 colours). It sits in the room with no retouching.
- **`remove_bg` erased the closed tomb.** Only the moss survived: the stone was close to
  the colours it keys out. Third failure of `remove_bg` in five tries. Ask for a flat
  background and key it with pixelwright, or use a style that returns transparency.
- **`rd_tile__scene_object` ($0.06) returns transparency** and kept the frontal camera,
  but with the open tomb as reference it drew a plainer, bluer box: two states of one
  object should come from the same style and seed.
- **Scale.** The 60 px knight only fits near the back wall (row 145); in front of the
  door the scene asks for about 100 px. Character sizes have to be drawn per scene depth.
- Results: project files `m7/rd-cripta-cerrada-abierta-x2.png` and the three tomb PNGs.

### Eye-level tomb after `pw scene analyze` (2026-11-18, $0.18)

The owner saw the props from above and the knight floating. `pw scene analyze` put the
crypt's horizon at row 139 (the first guess was 100), so the camera is low and props
should show only their front face. `rd_pro__fantasy` 96x40 with that prompt ("straight
side-on, at eye level ... neither its top nor its underside shows", flat magenta
background, keyed by colour) drew the sarcophagus frontal at eye level, matching the
floor. It came out 39 px tall where 22 px was asked: check the size of each prop.
On the marked floor, with `--guides`, nothing floats.

- A request killed by a client timeout still runs and is charged; `GET /v2/inferences/tasks`
  lists recent tasks with their images, so the result can be recovered.
- `GET /v1/inferences/credits` returns the balance.
