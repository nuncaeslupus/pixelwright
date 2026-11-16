# Specification notes

_Exported 2026-11-16 · 3 notes._

> Send this file back to continue the review. Notes are embedded as data at the bottom
> so importing this file restores them in the reader.

## Specification

**§1 Problem statement**  `SPEC §1`
> ¶ _“[ ] Every step of the flow (section 2.2) names exactly one actor (script, Claude or per…”_
>
> Let's replace Claude by any AI, but yes, let's take advantage of Claude tools, like following up the app results.

**§1 Problem statement**  `SPEC §1`
> ¶ _“[ ] No version is ever overwritten: versions_written == versions_on_disk after any sequ…”_
>
> Maybe keeping absolutely ALL versions could be too much. Maybe a checkbox checked by default?

**§2.1 Concepts**  `SPEC §2.1`
> ¶ _“Concept What it is On disk Project The art for one game. Holds the style: palette, canv…”_
>
> One palette for a game can be too little. Rather palettes or palettes associated with each images. For example, backgrounds.
> About versions, is it possible do some kind of diff for images? So they don't take too much space if only a pixel was modified.

<!-- SPEC-NOTES-DOC pixelwright-spec-v1 -->
<!-- SPEC-NOTES-DATA
{"s-spec-1~v8wqro":"Let's replace Claude by any AI, but yes, let's take advantage of Claude tools, like following up the app results.","s-spec-1~v8wqro~q":"[ ] Every step of the flow (section 2.2) names exactly one actor (script, Claude or per…","s-spec-1~1h3am48":"Maybe keeping absolutely ALL versions could be too much. Maybe a checkbox checked by default?","s-spec-1~1h3am48~q":"[ ] No version is ever overwritten: versions_written == versions_on_disk after any sequ…","s-spec-2-1~qlef8y":"One palette for a game can be too little. Rather palettes or palettes associated with each images. For example, backgrounds.\nAbout versions, is it possible do some kind of diff for images? So they don't take too much space if only a pixel was modified.","s-spec-2-1~qlef8y~q":"Concept What it is On disk Project The art for one game. Holds the style: palette, canv…"}
-->