# Scene norms

Rules learned from test scenes (a candle-lit crypt and a real city square) made to improve
pixelwright. They grow with every review round. The how-to is in [scenes](scenes.md) and
[painted scenes](painted-scenes.md); this page says what a good scene needs.

## Method

1. Write a brief first: what must be there, the mood, and which liberties are allowed.
   Update it after every review round.
2. Gather references: own photos, free-licence photos, a map or top view, street-level
   views. Copyrighted references are for looking only; they never enter a repository.
3. Draw a line sketch at game resolution with the camera worked out, and review the
   composition before painting anything. It is the cheapest place to fix mistakes.
4. Paint by parts in one style. Review by zones and repaint only the zones marked.
5. Decide colour late, and animate last, as separate layers.

## Camera and scale

6. Every scene uses the same camera height: eyes at 1.6 m, frontal view unless the scene
   needs another (`pw scene` also knows three-quarter and side). The horizon runs
   through the eyes of every standing character.
7. A person's height in pixels is about 1.09 × (feet row − horizon row). A scene only
   stores its horizon (`pw scene scale`).
8. Characters come in two or three hand-drawn sizes; a close scene shows the large one
   because the camera is near, not because the rule changes. Scale a size by at most
   about 15 %; pixel art does not survive larger factors.
9. Do not force the perspective to fit something in. A slight push to reveal a key
   feature is fine; otherwise leave the object out.
10. Open the frame just enough to show where the space ends (an angled side wall), even
    if characters get a little smaller.

## Composition

11. Idealise, do not copy: the place stays recognisable, every key element roughly in
    place, and objects move so that nothing important hides anything else.
12. Scrolling scenes (640 px = two screens of 320): the cut between screens never falls
    on a corner between buildings. Something of the next area shows on the first screen,
    so the player sees they can go there.
13. The main elements (a fountain, a portal) sit centred and symmetric, with a flat side
    towards the camera.
14. The foreground holds somewhere to be: café tables, benches, places for characters
    to sit.
15. Objects lean along their wall (a bike parallel to the tunnel wall) and never block
    entrances or paths.
16. Passages (arches, tunnels) are never seen end to end: the tunnel turns and only part
    of the exit shows, so the wall clearly continues.
17. Tree crowns never cover the focal points; they may be simpler or lower than in
    reality. Foreground framing elements stay sharp pixel art: darker, never blurred.
18. Reality may change for the game (a gate becomes a bar) when it gives the story room.

## Light and colour

19. The sun's direction comes from the real map. Shadows are computed from the sun
    (direction and height), not placed by eye; leaf shadows included.
20. Each wall gets its tone from how it faces the sun; the wall facing it most is the
    lightest.
21. Objects keep their own shading on top of cast shadows: the side towards the sun
    light, the far side dark.
22. An interior seen from outside (a tunnel): dark inside, a patch of sun on the floor at
    the entrance, the exit lit.
23. Use more contrast and accent colour than reality; real places photograph monotonous.
24. Static light is painted. Moving light (flames) is a mask driven by one curve shared
    with the flame it belongs to.

## Fidelity and detail

25. Recognisable pieces (a fountain, a portal, an arch) are drawn from reference photos
    with measured proportions.
26. Surface detail (shrapnel scars, cracks) respects openings: never on doors or windows,
    and it thins out away from its focus.
27. Whatever must be exact (scars, paving, joints) is its own layer, drawn, not left to
    the model.

## Pixels and generation

28. Painting at high resolution and shrinking gives blur, not pixels. Use a pixel-art
    LoRA at 1024 px and reduce to 320×180, or build at native size.
29. Image-to-image from a photo copies it at low denoise and invents at high denoise.
    Structure comes from a clean hand-drawn line sketch through ControlNet, never from
    edges detected in a photo.
30. Empty outlines get filled with the wrong material: draw texture hints (bark, cobbles)
    in the sketch.
31. Painted scenes keep 128 colours, and the approved scenes feed one game palette
    ([painted scenes](painted-scenes.md)); every frame snaps to it.
32. An animation loop lasts a common multiple of all its cycles, so nothing jumps at the
    loop point.

## Style

33. Define style with measurable numbers: palette size and ramps, hue shift in shadows,
    contrast and saturation, outlines, smallest pixel cluster, dithering, light direction
    and tones per material. Extract them from an approved scene, apply them to a new one
    with another palette, and check the result against them.
