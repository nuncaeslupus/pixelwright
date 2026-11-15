# Aseprite helpers

Lua scripts that connect Aseprite to a pixelwright workspace. They call the `pw` CLI,
so `pw` must be on `PATH` (or pass `pw=<path>` as a script parameter).

- `send_to_pixelwright.lua`: saves the active sprite as a new draft version of an asset
  and writes a history note (`asset`, optional `note`, `parent`, `workspace`).
- `load_version.lua`: opens a version (default: latest) of an asset (`asset`, optional
  `version`, `workspace`).

Install: copy `scripts/` into Aseprite's scripts folder (*File > Scripts > Open Scripts
Folder*), then *File > Scripts > Rescan*. Run them from the menu (a dialog asks for the
parameters) or headless, e.g.:

```
aseprite -b hero.aseprite --script-param asset=hero --script-param note="fixed the hands" \
  --script send_to_pixelwright.lua
```

Python wrapper: `pixelwright.io.aseprite_cli` (`export`, `run_script`); set
`PW_ASEPRITE` if the binary is not on `PATH`.
