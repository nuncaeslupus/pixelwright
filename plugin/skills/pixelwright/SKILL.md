---
name: pixelwright
description: Answers the person's requests in a pixelwright project — critique a version, propose fix images, reply — using the pw CLI. Use when a folder has pixelwright.toml, when `pw requests` lists work, or when the person asks you to review their pixel art.
---

# pixelwright: critique and fix

pixelwright turns any image into clean pixel art in steps: **scripts** (normalise, check),
then **you** (critique and propose fixes), then **the person** (decides in the app). The
person never talks to you through the app directly: requests wait as issues with target `ai`.

## Find the work

- `pw requests --json`: every request waiting on you (asset, issue id, message, areas, replies).
- `pw status --json`: each asset's state and single next step.

## Answer one request

1. Read it: `pw issues <asset> list --state all --json`. Areas are `[x, y, w, h]` boxes in
   native pixels of the version named in the issue.
2. Look at `assets/<asset>/versions/<latest>.png` (and the inputs for intent). Respect the
   asset's palette (`style/palettes/<name>.gpl`, from `pw status`/category settings): use only
   palette colours.
3. Write a candidate PNG of exactly the same size as the latest version. Change only what
   the request is about; keep every other pixel identical, so several fixes can be accepted
   together.
4. `pw fix <asset> propose --ids <issue-id> --file <candidate.png> --by ai --json`.
5. If the request is unclear or impossible, reply instead:
   `pw issues <asset> reply --id <issue-id> --by ai --message "..."`.

A person's reply after your fix means "try again": read the whole thread first.

## Critique on your own (when asked to review)

`pw check <asset>` raises script issues. Add yours with
`pw issues <asset> raise --by ai --kind critique --message "..." --box x,y,w,h`, then
propose a fix for each one you can solve.

## Limits

- At most 3 fix attempts per issue; after that, reply and explain.
- A rejection reason is a style lesson: do not repeat what was rejected.
- Never run `pw fix ... accept`, `pw finish` or reject on the person's behalf.
