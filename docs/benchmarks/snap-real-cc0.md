# snap on real CC0 pixel art

Date: 2026-11-15. Images are not committed; they were fetched from opengameart.org
(CC0 entries only) for a one-off run.

## Set

9 CC0 sheets: top-down sprites (16 px), roguelike tiles and monsters (32 px), two RPG
icon sheets, two platformer tilesets, three parallax/environment backgrounds (with
gradients). Alpha composited over a flat dark color; sheets already stored at an exact
integer upscale were reduced to native first. 4 random crops per sheet (32-64 x 24-48
native px, at least 4 colors), each upscaled x2..x12 with five degradations (clean,
blur sigma = scale/4, JPEG 70, noise sigma 5, random mix as in `fixtures.synth`) and a
random offset: 1980 cases. Pixel accuracy as in `tests/core/test_snap.py`.

## Results

One sheet (an industrial background) is itself a lossy x2 preview, not native art; snap
reports its real x2 grid, so its cases are excluded below.

| | scale-exact | pixels |
|---|---|---|
| before, excluding the x2 preview | 97.3% | 93.5% |
| clean | 100% | 100% |
| noise sigma 5 | 92.9% | 89.4% |
| after the multiple check (all 9 sheets) | 89.9% (was 89.0%) | 86.1% (was 85.1%) |

Main failure before: noise at x8-x12 on gradient backgrounds picked half the scale
(12 -> 6, 10 -> 5). Off-grid noise peaks lower the raw on-grid share, and chance
normalization then favors a divisor. Fix: after picking a scale (> 2), a multiple of it
that keeps >= 80% of its raw on-grid share and passes the inner-error check wins.
x10: 85.0 -> 89.4%, x12: 89.4 -> 94.4%; no other scale moved by more than one case;
synthetic set unchanged (98.75% scale-exact).

## Remaining weak spots

- x2 with JPEG or blur (about 81% scale-exact): picks x4 or x8.
- The set is modern short-palette art. 256-color VGA adventure-game backgrounds
  (dithering, soft lighting gradients) are not covered yet; a synthetic low-contrast
  dither case now pins the large-scale behaviour (`test_noisy_low_contrast_dither_*`).
