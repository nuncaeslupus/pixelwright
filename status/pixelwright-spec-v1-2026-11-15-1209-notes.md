# Specification notes

_Exported 2026-11-15 · 13 notes._

> Send this file back to continue the review. Notes are embedded as data at the bottom
> so importing this file restores them in the reader.

## Specification

**§1 Problem statement**  `SPEC §1`
> ¶ _“[ ] Local operations (snap, quantize, all checks, render previews) on a 384x216 image f…”_
>
> Size of images must be random. It could be s character or a sprite...

**§1 Problem statement**  `SPEC §1`
> ¶ _“[ ] Quality bar (judged by the owner): from a Wacom sketch, one 320x180 background is a…”_
>
> Again, size can just be orientative and for backgrounds. Characters and animations are also in the plan. Also, checking how a character looks against a background is another possible task. Even how a character colors change when it moves from a lighter to a darker place. The tool must help creating pixel art, but it should be able to add some effects while keeping the pixel art and palettes. Output return can be images or animations or both. Or even a character moving through a background.

**§1 Problem statement**  `SPEC §1`
> ¶ _“[ ] Privacy: a repository check (gitleaks plus a deny-list of personal names and other …”_
>
> A dent list is always a bad idea, as it already included the list of words to avoid.

**§2 Systems & Impact**  `SPEC §2`
> So it will be used in the game repo. It must be able to adapt to game directory structure and to differentiate between experiments and final result. The repo may want to keep both.

**§2.1 Actors and roles**  `SPEC §2.1`
> How input images are generated is important so that they can be then exported int pixel art: Style, palettes... Getting a similar style is very important.

**§2.2 Workflows**  `SPEC §2.2`
> ¶ _“Style coherence: a project style guide (palette families, ramp rules, outline policy, l…”_
>
> Good. This must be part of the workflow. Defining the style must be done at the beginning (it can change) and per project with the help of AI too.

**§2.3 Workspace layout**  `SPEC §2.3`
> Don't forget a place for style, experiments  drafts...

**§4 Recommendation**  `SPEC §4`
> ¶ _“[ ] Native canvas: 320x180 (x6 to 1080p) or 384x216 (x5)? Research leaves it to the spe…”_
>
> Exactly  configurable with default.

**§4 Recommendation**  `SPEC §4`
> ¶ _“[ ] Licence for this repository (MIT, like the owner's other tools, is the proposal).”_
>
> Ok.

**§4 Recommendation**  `SPEC §4`
> ¶ _“[ ] Aseprite: compile from source or buy? Either works; the bridge does not depend on i…”_
>
> Compile.

**§4 Recommendation**  `SPEC §4`
> ¶ _“[ ] Monthly API budget cap for M3 (proposal: 20 USD for the first benchmark).”_
>
> Yes 

**§4 Recommendation**  `SPEC §4`
> ¶ _“[ ] Should the plugin live in this repository (plugin/) or in a separate one? Proposal:…”_
>
> Yes, here.

**§4 Recommendation**  `SPEC §4`
> We may need a screenshot spec for the viewer  but a it's time 

<!-- SPEC-NOTES-DOC pixelwright-spec-v1 -->
<!-- SPEC-NOTES-DATA
{"s-spec-1~yxsdze":"Size of images must be random. It could be s character or a sprite...","s-spec-1~yxsdze~q":"[ ] Local operations (snap, quantize, all checks, render previews) on a 384x216 image f…","s-spec-1~1vi7euk":"Again, size can just be orientative and for backgrounds. Characters and animations are also in the plan. Also, checking how a character looks against a background is another possible task. Even how a character colors change when it moves from a lighter to a darker place. The tool must help creating pixel art, but it should be able to add some effects while keeping the pixel art and palettes. Output return can be images or animations or both. Or even a character moving through a background.","s-spec-1~1vi7euk~q":"[ ] Quality bar (judged by the owner): from a Wacom sketch, one 320x180 background is a…","s-spec-1~1jzzt3n":"A dent list is always a bad idea, as it already included the list of words to avoid.","s-spec-1~1jzzt3n~q":"[ ] Privacy: a repository check (gitleaks plus a deny-list of personal names and other …","s-spec-2":"So it will be used in the game repo. It must be able to adapt to game directory structure and to differentiate between experiments and final result. The repo may want to keep both.","s-spec-2-1":"How input images are generated is important so that they can be then exported int pixel art: Style, palettes... Getting a similar style is very important.","s-spec-2-2~cf3qyn":"Good. This must be part of the workflow. Defining the style must be done at the beginning (it can change) and per project with the help of AI too.","s-spec-2-2~cf3qyn~q":"Style coherence: a project style guide (palette families, ramp rules, outline policy, l…","s-spec-2-3":"Don't forget a place for style, experiments  drafts...","s-spec-4~1ybcs8j":"Exactly  configurable with default.","s-spec-4~1ybcs8j~q":"[ ] Native canvas: 320x180 (x6 to 1080p) or 384x216 (x5)? Research leaves it to the spe…","s-spec-4~1csi8uz":"Ok.","s-spec-4~1csi8uz~q":"[ ] Licence for this repository (MIT, like the owner's other tools, is the proposal).","s-spec-4~1osjj56":"Compile.","s-spec-4~1osjj56~q":"[ ] Aseprite: compile from source or buy? Either works; the bridge does not depend on i…","s-spec-4~ql7hm2":"Yes ","s-spec-4~ql7hm2~q":"[ ] Monthly API budget cap for M3 (proposal: 20 USD for the first benchmark).","s-spec-4~ufqvh3":"Yes, here.","s-spec-4~ufqvh3~q":"[ ] Should the plugin live in this repository (plugin/) or in a separate one? Proposal:…","s-spec-4":"We may need a screenshot spec for the viewer  but a it's time "}
-->