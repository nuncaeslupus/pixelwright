---
name: zone-fix
description: Fix an open pixelwright issue only inside its region, re-check and mark it fixed. Use when an asset has open issues from checks, a critique, or the artist.
---

# Zone fix loop

Any complaint, from a detector, from you or from the artist, is an issue: a region in
native pixels, a rule id and a note. Fixes run only inside the region; the checks re-run
(`R-CRIT-3`).

1. `pw issue <asset> list --status open` and read each issue's note, rule and region.
   Issues by the artist (`author: human`) come first.
2. Choose the fix:
   - noise, stray pixels: `pw clean <asset> --mask <issue>` (add `--pairs` for 2-pixel
     clusters);
   - colors off the palette or banding: `pw quantize <asset> --mask <issue>`;
   - anything that needs drawing (shapes, values, lines): ask the artist to retouch it in
     Aseprite (`load_version.lua` opens the version with its layers, `send_to_pixelwright`
     brings it back as a new version), and say exactly what to change.
3. Add `--resolve` to `clean` or `quantize` to mark the issue fixed by the new version, or
   `pw issue <asset> resolve --id <issue> --version <new>` after a manual fix.
4. `pw check <asset>` on the new version, and confirm with `pw diff <asset> <old> <new>`
   that nothing changed outside the region and the rule's check improved. If it did not,
   reopen the question in the critique instead of stacking more fixes.

Pixels outside the mask stay identical; if a fix needs to touch more, raise a new issue
with the larger region rather than editing outside the old one.
