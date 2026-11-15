---
name: first-run
description: Walks a new pixelwright user through `pw tour`, then their first real asset, explaining each step in plain words. Use when the user is new to pixelwright, says it does not make sense yet, or asks how to start. Not for an ongoing session (review-loop).
---

# First run

The user is learning the tool. Explain before you act, one step at a time, in plain words;
no command lists without a reason. The full picture is `docs/guide/how-it-works.md`.

## 1. The tour

Run `pw tour --path pw-tour` (offline, free, a few seconds). It prints eight blocks, each
"what happened / why / look at". Do not paste them all back: summarise the loop in three
sentences (painter paints, code makes the pixels real and measures, Claude reviews, the
user decides), then open the result with `pw view --workspace pw-tour --open hillside`
and point at two things: the blurry painted v0001 next to the clean final version, and
the hint under the image that says what comes next.

Ask what was unclear before going on.

## 2. Check the setup

Run `pw doctor` and explain only the rows marked to fix, with the fix it gives. Local
painting needs ComfyUI (`docs/guide/comfyui.md`); paid providers need a key and are
capped by the monthly budget (`pw cost`).

## 3. Their first asset

1. `pw init <folder>` with the game's canvas, then `pw new <id> --kind <kind>`.
2. Ask for a sketch; `pw attach <id> <file> --as sketch`.
3. From here, run `pw next <id>` before each step and tell the user, in one line, what
   the step does and why, then run it. Stop at every review: the user looks in
   `pw view` and decides; never approve for them.
4. When `pw next` says done, hand over to the `review-loop` skill for later sessions.
