---
name: style-definition
description: Build or revise a pixelwright style guide with the artist - references, palette families and ramps, light and outline conventions, test assets. Use at the start of a project or when the artist wants to change the look.
---

# Style definition

The style guide (`style/style.yaml`) drives both generation and checks. It is versioned:
every change is a `pw style bump`, and assets made under an older version show as stale.

1. **References.** Collect mood references with the artist: their sketches, approved
   assets, and style notes about other games (notes only, never their pixels). Put the
   PNGs in `style/references/`.
2. **Palette and ramps.** `pw style propose --colors <n>` proposes a palette and hue-family
   ramps from the references (`style/palettes/proposed.gpl`, `proposed-ramps.yaml`); it
   changes nothing yet. Review the ramps with the artist against `R-PIX-2` (lightness
   rising, a hue shift along the ramp, no flat ramps). Adjust with `pw palette edit --name
   <file> --set i=RRGGBB --add RRGGBB --remove i --order ...`; the reply re-checks the
   ramps. `pw palette import --file <f>` takes a palette the artist already has.
3. **Conventions.** Agree light direction, outline policy, density and dithering, then
   write them in one bump: `pw style bump --changes '{"light": {...}, "outline": {...},
   "palettes": [...], "ramps": "palettes/ramps.yaml"}' --note "<why>"`.
4. **Test assets.** Make 3-5 small assets with the guide (`pw new`, the pipeline, `pw
   check`), list them in the guide (`pw style bump --changes '{"test_assets": [...]}'`)
   and run `pw style test`: one row per asset with its failed checks. The artist approves
   the look; the guide's version is then the one new assets record.
5. **Later changes.** Any bump lists stale assets in its reply; offer to re-check them with
   `pw style test --assets <ids>` or `pw check`.

`pw style show` prints the current guide and the stale assets.
