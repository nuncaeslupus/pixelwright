---
name: critique
description: Write a pixelwright critique for a version - pairwise against the previous best and approved references, every complaint tied to a region, a rule id and a proposed fix. Use after `pw check`, before asking the artist to review.
---

# Critique protocol

A critique is evidence for the artist, not a grade. Never give a bare 1-10 score; compare
(`R-CRIT-2`).

## Gather

1. `pw check <asset> --version <v>` writes `report.json`: each check's status, value and
   offending regions in native pixels. Detectors own pixel facts; do not re-measure by eye
   what a check measures.
2. Look at the version, not only the numbers: `pw render <asset> --version <v> --view
   upscale`, then `gray`, `values` and `silhouette`. `--view overlay` marks the flagged
   regions. From MCP the render comes back as an image.
3. Pick what to compare against: the previous best version (the latest approved one, or
   the parent) and the style's approved references. `pw diff <asset> <a> <b>` gives
   changed pixels, colors used and per-check deltas.

## Judge pairwise

For each comparison say which is better on: value structure and focal point (`R-VAL-1`),
depth (`R-DEPTH-1`), readability and silhouette (`R-READ-1`), palette and ramps
(`R-PIX-2`), clusters and noise (`R-PIX-3`), lines, banding, pillow shading. Say what got
worse as plainly as what got better.

## Write it down

Every complaint names a region, a rule and a fix (`R-CRIT-3`):

1. Make the region an issue: `pw issue <asset> add --version <v> --rule <R-id> --note
   "<what and why>"` with `--box x,y,w,h` (native pixels) or `--file mask.png`. Reuse a
   check's region box when it is the same problem.
2. Write `critique.md` and store it with `pw critique <asset> write --version <v> --file
   critique.md`:

```markdown
---
schema: pixelwright/critique@1
version: v0004
compared_to: v0003
verdict: better than v0003; two fixes before review
---
## Muddy focal area
issue: r-val-1-1
rule: R-VAL-1

The door and the wall share one value group; lift the door one ramp step.
```

`verdict` is one line the artist reads first. `pw critique <asset> show` reads it back.
