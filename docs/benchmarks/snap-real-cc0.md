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

## Adventure-game set (after the fix)

10 CC0 point-and-click images (eight 320x200 rooms or portraits, one 800x500 scene, one
creature sprite and a mockup; 7-76 colors), same protocol: 2200 cases, **97.5%
scale-exact, 95.5% pixels**. Worst sheet: a room with large flat walls (85.5%), where
few borders leave the grid underdetermined. Worst mode: blur (90.8% pixels).

## Remaining weak spots

- x2 with JPEG or blur (about 81% scale-exact): picks x4 or x8.
- No CC0 image found uses a full 256-color VGA palette with soft lighting gradients;
  a synthetic low-contrast dither case pins that behaviour at x12
  (`test_noisy_low_contrast_dither_*`, about half the seeds recovered, none on main).

## VGA adventure screenshots (study only)

Native 320x200-era room maps from four commercial 1990s VGA point-and-click games
(fetched from a map archive for this one-off run; not committed, not redistributed).
Stitched maps exceed 256 colors overall, but each crop has 4-200 colors, often with
dithering and close lighting shades. Same protocol: 9 maps, 1980 cases.

| | scale-exact | pixels (exact index) | pixels within RGB 12 |
|---|---|---|---|
| before | 94.8% | 81.6% | |
| after the uniformity guard | 96.5% | 83.1% | 92-100% per mode |

The multiple check of the previous fix over-picked twice the scale on blurred crops
(6 -> 12, 7 -> 14, 8 -> 16): art drawn mostly in 2x2 blocks keeps most borders on the
coarser grid. Guard: the multiple must also have an inner error no larger than the
pick's (+ 1 RMS). Blur 89.9 -> 92.2%, noise 94.2 -> 97.7%; synthetic set unchanged.

Exact-index pixel accuracy is low because VGA shading uses neighbor colors a few RGB
units apart, below the noise and JPEG error; within 12 RGB units the recovered cells
match. x2 stays the weakest scale (88%).
