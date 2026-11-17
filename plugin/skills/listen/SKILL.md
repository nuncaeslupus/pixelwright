---
name: listen
description: Keeps a session listening for requests from the pixelwright app with `pw wait` in the background, and answers them as they arrive. Use when the person says "listen", "wait for my requests", or opens a session to work alongside the app.
---

# Listen for requests from the app

The app cannot call you. It writes requests into the project; `pw wait` blocks until one
exists and costs nothing while it waits.

1. Run `pw wait --json` **in the background** (Claude Code: `run_in_background`). Optionally
   `--timeout 3600` so it ends after an hour of silence.
2. When it returns, read the JSON: `data.requests` lists every pending request.
3. Answer each with the `pixelwright` skill (propose a fix image or reply).
4. Start `pw wait` again. Stop when the person says so or after a timeout with no requests.

On demand instead: the person says "check pending" → run `pw requests --json` once.

## Session-start hook (optional)

So every new session says how many requests wait, add to the project's
`.claude/settings.json`:

```json
{"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "pw requests --hook"}]}]}}
```

`pw requests --hook` prints one line when something is waiting and nothing otherwise.
