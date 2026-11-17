# Working in a pixelwright project (for any AI agent)

This folder is a pixelwright project: it turns images into clean pixel art in steps.
Scripts run first, then the AI (you) critiques and proposes fixes, then the person decides
in the pixelwright app. Never edit files by hand: use the `pw` CLI (add `--json` for a
machine-readable envelope). Everything is plain files: `pixelwright.toml`, `assets/<category>/<asset>/`
with `asset.toml`, `inputs/`, `versions/vNNN.png`, `issues.jsonl` and `fixes/`.

## Your loop

1. `pw requests` — what the person asked you (open issues with target `ai`, or their replies).
   To wait for new ones without spending anything: run `pw wait` in the background; it
   returns as soon as a request exists.
2. For each request: read the asset (`pw status <asset>`, `pw issues <asset> list --state all`),
   look at the latest version image and the areas named in the request.
3. Make a fix candidate: write a full image of the same size as the latest version, changing
   only what the request is about, then `pw fix <asset> propose --ids <issue-id> --file <png> --by ai`.
4. If you cannot fix it, say why: `pw issues <asset> reply --id <issue-id> --by ai --message "..."`.
5. Optionally review new assets yourself: `pw check <asset>` raises script issues; raise your own
   with `pw issues <asset> raise --by ai --kind critique --message "..." --box x,y,w,h`.

Limits: at most 3 fix attempts per issue; stop when the person rejects twice for the same
reason and reply instead. Never accept, reject or finish on the person's behalf: `pw fix accept`,
`pw finish` and rejections are theirs.

## Commands

`pw init` · `pw add <category>/<name> --from <image>` · `pw colors <asset>` · `pw normalize <asset>` · `pw check <asset>` ·
`pw status [asset]` · `pw issues <asset> list|raise|reply|reject|mark-fixed` ·
`pw fix <asset> propose|accept|reject` · `pw undo <asset>` · `pw redo <asset>` ·
`pw star <asset> <version>` · `pw finish <asset> [version]` · `pw requests [--hook]` · `pw wait` · `pw open`
