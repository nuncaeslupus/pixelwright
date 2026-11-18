# Scenes in layers

One model call rarely draws a whole adventure scene with every object at the right scale.
`pw scene` builds it from parts instead: an empty background, props and characters, each
generated on its own and composed with one camera and one scale. Spec: `status/m7/spec.md`.

## 1. Describe the scene

```bash
pw scene new crypt --background scenes/crypt-bg --horizon 100 --door 152:104
```

This writes `scenes/crypt.toml`. Rows count from the top of the image.

- `horizon`: the camera's eye level. On a frontal room it is roughly where the floor
  lines would meet.
- `door`: where a door touches the floor and how tall it is. A person is 0.85 of a door
  (`person_to_door` changes it; an arched crypt door is closer to 0.7). Or give
  `person = { y, height }` directly.

**Check the horizon.** Generated backgrounds often disagree with themselves (a door drawn
close up on a floor seen from knee height). `pw scene analyze crypt` finds where the
floor's receding lines meet and gives that row as the horizon (`--apply` writes it); it
also says how high the camera is for your scale reference and warns outside 0.6-4 m.
Trust the floor over the door: props and characters stand on the floor.

**Mark the floor.** `floor = [[x, y], ...]` under `[scene]` is the walkable polygon.
Compose warns when a layer's base is off it (it would float), and
`pw scene compose crypt --guides` writes `crypt-guides.png` with the horizon (green), the
floor (yellow) and each base (cyan on the floor, red off it).

`pw scene scale crypt --at 170` then says how tall a person is with feet on row 170. The
rule is the ground plane: height grows linearly with the distance from the horizon.

## 2. Generate the parts with the same camera

```bash
pw generate props/tomb --scene crypt --at 150 --height 40 --prompt "a stone sarcophagus"
```

`--scene` adds the camera (frontal, three-quarter or side), where the eye level crosses
the object (so the model knows whether its top shows), and its size next to a person.
`pw scene prompt crypt --at 150 --height 40` prints those words for any other tool.

Characters: `pw scene sizes crypt` lists the heights to draw so every depth is covered,
each with its prompt. Pixel art cannot be downscaled: each smaller size is a simplified
redraw (with Retro Diffusion, the big size as a reference image works well).

## 3. Place and compose

```toml
[[layer]]
name = "tomb"
asset = "props/tomb"
at = [150, 158]            # bottom centre, where it touches the floor
states = { open = "props/tomb-open" }
frames = { open = 8 }      # an animated state: a horizontal strip of 8 frames

[[layer]]
name = "knight"
sizes = ["chars/knight", "chars/knight-m", "chars/knight-s"]
at = [70, 172]
```

```bash
pw scene compose crypt                         # export/scenes/crypt.png + crypt.json
pw scene compose crypt --state tomb=open --gif # the opening, as an animated GIF
```

- Layers draw far to near by their base row; `z = 1000` puts one in front (a pillar);
  a layer with `z` gets no contact shadow.
- `--state` applies to layers with states; character layers pick their size by depth.
- With `--viewport`, the JSON keeps world coordinates.
- Each grounded layer gets a contact shadow made from darker colours the scene already
  has; `shadow = false` or `--no-shadows` leaves it out.
- A character uses the size nearest to the scene's scale at its row, pixel for pixel, and
  the result warns when no size is within 15 %.
- `crypt.json` lists where every layer went, for a game engine.
- For an animation that should stay open, ask the model for one that ends open, or draw
  the open state as its own asset.

## 4. Scrolling scenes

Set `width = 640` and give two or more backgrounds with `x`. Where tiles overlap they meet
along the seam where they differ least; nothing is blended, so no colour is invented.
`--viewport 160` crops the 320-wide view starting at column 160.
