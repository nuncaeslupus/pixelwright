---
name: style
description: Sets up or changes a pixelwright project's look — palettes, canvas sizes per category, check levels, learnt rules — by talking with the person. Use when a project is new, when the person describes the style they want, or when they ask to change palettes or categories.
---

# Define the style

The style lives in plain files the person can read:

- `pixelwright.toml`: `[project]` (name, `export` folder, `keep_all_versions`), default
  `[canvas]`, `[palettes] default`, `[rules]` levels (`error` | `warn` | `off`).
- `style/palettes/<name>.gpl`: the palette library (GIMP palette format).
- `assets/<category>/category.toml`: per category `kind`, `palette` or `palettes`,
  `[canvas]` and `[checks]`. The nearest folder wins: asset, then category, then project.
- `style/rules.toml`: rules learnt from rejections (written by
  `pw issues <asset> reject --promote`; do not edit by hand without asking).

## Steps

1. Ask what the art is for, its size on screen, mood and references. Start a new project
   with `pw init` if there is none.
2. Propose 1–3 palettes (8–32 colours each) with names; write them as `.gpl` files.
3. Propose categories (e.g. scenes, characters, props) with canvas sizes; write each
   `category.toml`.
4. Show the result on one real image: `pw add <category>/<name> --from <image>`, then
   `pw normalize <asset>` and `pw check <asset>`; ask the person to look in the app (`pw open`).
5. Adjust until the person is happy. Keep their words in the brief, not your own.
