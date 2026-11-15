---
name: review-loop
description: Start of every pixelwright session and after each artist action. Reads the inbox, then moves each asset one step through check, critique, review and fix. Use when working on pixel-art assets in a pixelwright workspace.
---

# Review loop

pixelwright is the craftsman (transforms, measurements, renders, bookkeeping); you are the
art director. The artist decides. Work through the MCP tools (`pw mcp`, one tool per
command) or the `pw` CLI with `--json`; both return the same envelope.

## 1. Start from the inbox

Run `pw inbox --reader claude`. It lists what the artist did since your last entry: new
versions (an Aseprite retouch arrives as `attach`), decisions, issues they drew, notes.
Then `pw status` shows every asset's stage, newest version, flagged checks and open issues.

Handle, in this order:

1. **Rejections** with a note: read the note and the issues on that version, plan a fix
   (see the `zone-fix` skill).
2. **New issues drawn by the artist** (`author: human`): each is a region and a note; fix
   inside it.
3. **New versions from the artist**: run `pw check <asset>` and critique them (see the
   `critique` skill) before changing anything; they may have fixed issues by hand.
4. **Assets waiting for a decision**: nothing to do; tell the artist which ones and why
   they are ready (check summary, critique verdict).

## 2. Move one asset one step

| Asset state | Next step |
|---|---|
| source attached, not native | `pw snap <asset>`, then `pw quantize <asset>`, then `pw clean <asset>` |
| new version without a report | `pw check <asset>` |
| report, no critique | write one (`critique` skill), `pw critique <asset> write` |
| open issues | `zone-fix` skill |
| approved | `pw export <asset>` when the artist asks for it |

Never approve or reject yourself: decisions belong to the artist (`R-CRIT-4`).

## 3. Show the artist

`pw view --open <asset>/<version>` opens the viewer on the version to review; from MCP it
runs in the background and returns the URL. Say in one line what changed and what you
want them to look at. `pw history <asset>` and `pw diff <asset> <a> <b>` back up any claim
about what changed.
