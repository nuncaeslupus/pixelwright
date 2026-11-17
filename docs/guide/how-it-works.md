# How pixelwright works

pixelwright turns any image (a sketch, an AI painting, a photo) into clean pixel art for
a game. Scripts make the pixels real and measure them; an AI agent fixes what you ask;
you decide when an asset is finished.

Try it first: `pw open` with no project opens a sample project with two assets, already
cleaned, each showing its next step.

## The flow

1. **Add an image.** In the app, *+ Add images* and pick a category (scenes, characters,
   ... or *+ New category…*). Or save the file straight into `assets/<category>/`; the
   app picks it up. On the command line: `pw add scenes/harbour --from harbour.png`.
2. **Scripts run.** `pw normalize` finds the pixel grid, maps colours to the palette and
   removes stray pixels into a new version; `pw check` raises an issue for each problem
   it measures. For jaggy straight lines (steps like 1,2,1,3) the scripts also propose
   the fix: the same lines redrawn with even steps, for you to accept or reject. The app runs both as soon as an image arrives. An image with no pixel
   grid near the canvas size (a painting, a photo) is first reduced to the canvas: brush
   texture is flattened while edges are kept, and specks of 1-4 pixels left after the
   palette are folded into the shapes around them. A sprite painted on one flat colour
   (image models cannot paint transparency, so ask for a magenta background) has that
   colour made transparent and is cropped to the figure before it is reduced, keeping
   its dark outlines. With
   no palette in the project, one is discovered: 16 colours plus up to 8 *accents*,
   small colours that stand out where they are (a lit window, the moon, an eye).
   `pw colors <asset>` shows that analysis before normalising: the colour groups, the
   accents and `analysis/importance.png`, a heatmap of where colour matters most.
3. **Review.** Open the asset, compare versions (hold Space), select areas and write what
   is wrong. *Ask the AI* sends it as a request; the AI answers with a fix (a new image).
4. **Decide.** Accept or reject each fix; accepting several makes one new version. Undo
   and redo write new versions too, so nothing is ever lost. Retouch by hand with
   *Open in Aseprite*; the saved file comes back as a new version.
5. **Finish.** *Finish with vN* writes the final image and copies it to the export folder
   (`export/<category>/<asset>.png` by default).

Every asset card shows its single next step and who owes it: you, the AI or the scripts.
`pw status` prints the same list.

## The AI side

Any agent works the project through `pw` (see `AGENTS.md`, written by `pw init`). With
Claude Code, the plugin's `listen` skill runs `pw wait`, answers each request with
`pw fix <asset> propose`, and never finishes an asset for you. Rejecting an issue as a
style rule (`pw issues <asset> reject --promote`) writes the reason to `style/rules.toml`,
so it is not raised again.

## Glossary

| Word | Meaning |
|---|---|
| project | a folder with `pixelwright.toml`; settings resolve by nearest folder (`asset.toml`, `category.toml`) |
| category | a folder under `assets/` (scenes, characters...); the left panel of the app |
| asset | one game image, a folder under its category with `inputs/` and `versions/` |
| version | one image of an asset (`v001`, `v002`...); every change makes a new one |
| issue | something to fix on a version, raised by a script, the AI or you |
| fix | a proposed new image for one or more issues; you accept or reject it |
| state | where an asset stands: processing, in review, finished |

## Your first real project

1. `pw init my-game` (or *Open a project folder…* in the app), then put a `.gpl` palette
   in `style/palettes/main.gpl`.
2. `pw open my-game` and add images.
3. Old M0–M3 workspace? `pw migrate` converts it in place and keeps the old files as
   `pixelwright.toml.bak` and `assets.bak/`.

## Painting with an image model

A provider is one more input source. `pw generate scenes/harbour --provider comfyui
--prompt "a harbour at night"` paints from the newest input (or from nothing, with
`--init none`); each image lands in `inputs/` and the scripts normalise it into a version.
`pw generate <asset> --issue <id>` repaints only that issue's areas and proposes the result
as a fix. Settings live in `pixelwright.toml`: `[providers.<name>]`, `[presets.<name>]`
(preamble, negative, scale), `[defaults] provider = "..."` and `[budget] monthly_usd`;
reference images go in `style/references/`. `pw cost` shows the month's spending and
`pw doctor` what is set up. Local painting on your GPU: [comfyui.md](comfyui.md).

### The game's style kit

Every prompt carries the game's style, so "an empty old bar with a stage and a piano
under spotlights" comes back already in it. The kit is the asset's palette and canvas
(sent as hex codes and as the native size) plus, in `pixelwright.toml`:

```toml
[style]
preamble = "Moody 90s point-and-click adventure"
rules = ["1-px dark outlines", "light from the upper left"]

[style.scenes]          # a category can override the preamble and rules
preamble = "Night interiors, warm lamps"
```

and the images in `style/references/` and `style/references/<category>/`, sent as
references where the provider takes them. Normalise then uses the same palette and
canvas. `pw style show scenes` prints the kit and the exact words sent.

No palette file yet? `colors = 248` in a `category.toml` or `asset.toml` builds the
palette from each input instead (accents included), and the prompt asks for at most
that many colours.


Image models read a list of hex codes as a mood, not a limit, so for a provider that
takes no palette the prompt names only the palette's size; show the colours as an
image instead. `pw palette discover --asset scenes/tavern scenes/street --colors 32
--name base --swatch` builds one palette shared by several assets (or `--images` files)
and saves it as `style/palettes/base.gpl` plus a swatch in
`style/references/palette-base.png`, which then goes with every prompt.

To design the game's base palette instead of extracting it, `pw palette ramps --name base
--swatch` builds one ramp of shades per key colour, shadows turning towards blue-violet
and lights towards yellow, plus a shared near-black and near-white. It starts from an
`adventure` preset (skin, hair, wood, stone, metal, foliage, cloth, gold, fire); add or
replace keys with `--keys skin-light=f0c39c moss=4f6b2e`, or `--preset none` to start
from scratch, and `--steps 4` for shorter ramps.
