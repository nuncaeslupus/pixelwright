# pw on real VGA adventure screens (2026-11-17)

Question: does `pw normalize` + `pw check` leave correct, professional pixel art alone?
Images are not committed: 10 crops of 320x180 from vgmaps.com maps (Fate of Atlantis,
Loom, Simon the Sorcerer 1-2, Beneath a Steel Sky), native and enlarged x3 (nearest).
Each crop has 274-785 distinct colours (the maps mix room palettes).

## Results

- **Grid: correct.** Native and x3 inputs gave the same 320x180 result in all 10 cases.
- **Colours: too lossy.**
  - With no project palette, `normalize` discovers 16 colours (+ accents), so 300-800
    colours become 18-22. Exact pixels 0-31%.
  - With a palette discovered from the image itself (`--colors 248`), discovery merged
    near shades down to 35-171 colours. Exact pixels 10-41%, within RGB 16 80-99%.
  - Visible shifts: white turned pale green and a white robe turned cyan (Simon 2).
- **Checks: noisy.** Every image got the same three warnings: orphans (1,900-6,100),
  line-runs (230-670) and banding (16-100). On professional art these are false positives:
  the checks are calibrated for 16-32 colour sprites, not for dithered 256-colour scenes.

## To do (not planned)

1. When the input is already pixel art on its grid and has at most 256 colours, keep its
   colours exactly (no discovery and no merge), unless a project palette is set.
2. Let discovery reach 256 colours without merging distinct VGA shades, and never move
   white or greys to a hue.
3. Scale the check thresholds by palette size and image area, or report them as density.
   Use these real screens as a "should pass" fixture set, kept local only.
