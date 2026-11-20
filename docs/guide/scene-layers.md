# Scenes for an engine: layers, lights and art direction

`pw scene compose` bakes a scene into one picture or GIF. A game engine wants the parts:
a static background, the moving things as sprite strips, and the light as data. `pw scene
layers` writes exactly that. The animated GIF it also writes is only a preview of what the
engine will show.

```bash
pw scene layers crypt --zoom 3
```

It writes `export/scenes/crypt-layers/`:

| File | What it is |
|---|---|
| `background.png` | The painted scene, static light included, with the painted flames removed |
| `flame-<i>.png`, `<layer>.png` | One horizontal sprite strip per flame and per `[[layer]]` |
| `light-<i>.png` | One greyscale mask per `[[light]]`: how much of its flicker each pixel takes |
| `floor.png` | The floor mask: the floor takes the flicker `floor_gain` times as strongly |
| `manifest.json` | Positions, frames, fps, z order, lights and their curves (schema below) |
| `preview.gif` | The scene composed the way an engine would, every frame snapped to the palette |

The command also reports three checks, stored under `checks` in the manifest:

- `preview_frames`: the preview's length;
- `off_palette`: how many colours fell outside the scene palette (always 0);
- `brightness_swing`: how much the mean brightness moves over the loop. Around 10-15 % reads
  as a living torch; 3 % is invisible.

## The scene file

`pw scene layers` reads the same `scenes/<name>.toml` as `compose`. It adds these settings:

```toml
[engine]                     # all optional
fps = 10
amplitude = 0.26             # flicker strength
tint = [1.0, 0.92, 0.85]     # per channel: red moves most, so brighter reads warmer
floor_gain = 2.2             # the floor answers the flicker more than the walls
# frames = 240               # preview length; default: the common loop of every cycle
# seed = 5                   # the curves' phases

[[light]]
at = [124, 57]
period = 48                  # frames of this light's loop (defaults 48, 60, 48, ...)

[[flame]]
box = [117, 39, 15, 27]      # where the painted flame is
height = 14                  # height of the flame drawn in its place (default: the box)
# light = 0                  # the light it follows (default: the nearest)
```

## How each part is made

**One curve per light.** A light's level is
`0.6 sin(q+p0) + 0.3 sin(3q+p1) + 0.2 sin(5q+p2)` over its period. Its flame follows the same
curve: a brighter moment makes the flame up to 10 % taller and pushes its colours towards
yellow. A flicker that does not match its flame reads as wrong. The manifest stores the curve
and which flame it `follows`, so the engine needs no formula.

**Light masks have two terms.** A tight term (sigma = width / 10) is weighted by how
torch-lit each pixel already is, so each torch owns its side of the room. A wide, weaker term
(sigma = width / 3.5, 0.6 of it, at least 0.35 even on cool pixels) makes the whole room
breathe with the light. Without it, mean brightness swings about 3 % instead of 13 %.

The engine applies a light as follows:

```text
light = amplitude * (scale * curve[t] + offset) * mask
pixel = background * (1 + light * tint)
```

`scale` is 0.8 and `offset` is 0.3, so the light brightens more than it darkens. The dim end
stays close to the painted image.

**Flames are drawn, not warped.** The painted flame (its yellow-to-white pixels) is cut out.
The wall behind it is continued from the same row. A flame is then drawn from a shape:

- a teardrop, widest a third of the way up;
- a tongue that sways more the higher it goes;
- rising heat noise that closes the loop;
- no dark rim, since the ramp ends in orange.

Warping the painted pixels looked worse.

**Every colour comes from the palette.** The flame's ramp is the palette's nearest colours to
a pale-core-to-orange ramp. Never write effect colours by hand: hand-picked blues snapped to
pink. Each preview frame is snapped to the scene palette after the lights multiply it.

**Loops close.** The preview lasts a common multiple of every cycle (light periods and strips).
A preview that cuts a cycle makes drops vanish mid-wall and flames jump, so a `frames` value
that is not a common multiple is refused. Choose periods with common factors: 48 and 60 frames
meet at 240 (24 s at 10 fps); 46 and 62 would need 1426.

## Art direction

- **Static light is painted.** The background already carries the torch glow, the shadows
  and the colour of the light. The engine only adds the flicker on top.
- **Dynamic light and particles belong to the engine.** Flicker, sparks, and characters
  tinted as they walk past a torch come from the light masks and the manifest. They are not
  baked into frames: a baked GIF cannot react to a character.
- **The palette is VGA-style.**
  - Each room has its own palette of about 200 colours.
  - The whole game shares a fixed band of 32-48 colours (protagonist, UI, common props), so
    shared things look the same in every room.
  - Snap every generated frame to the room palette plus the band.
- **Measure, don't guess.** Read the wall-floor joint off a contrast-stretched zoom, along its
  most legible stretch. A straight line guessed from two points put a puddle on the wall.
- **Stylised beats exact.** A geometrically exact torch reflection landed where the eye did not
  expect it. A soft sheen (reflectivity 0.3, 1 px blur) and a warm vertical glint under the
  light read better.

## Not yet in `pw scene layers`

The crypt prototype had these too. They are planned as follow-ups:

- water: puddle masks on the floor, soft reflection, a glint under each light, drips with a
  half ring at the water line, and the exact mirror rule kept in the manifest for engines;
- particles: a spark emitter per flame;
- the wall-floor seam from `pw scene analyze`, to replace the `floor` polygon drawn by hand.
