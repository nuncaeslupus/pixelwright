"""`pw scene`: scenes built in layers (spec `status/m7/spec.md`)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from pixelwright import scene as sc
from pixelwright.cli.flow_commands import _guard, _project
from pixelwright.cli.registry import Outcome, Param, PwError, command

ACTIONS = ("new", "show", "analyze", "scale", "sizes", "prompt", "compose")


def _states(raw: list[str]) -> dict[str, str]:
    out = {}
    for item in raw:
        layer, sep, state = item.partition("=")
        if not sep or not layer or not state:
            raise PwError("usage", f"--state takes layer=state, got {item!r}", exit_code=2)
        out[layer] = state
    return out


@command(
    "scene",
    "scenes in layers: new, show, analyze, scale --at Y, sizes, prompt --at Y, compose",
    Param("action", positional=True, required=True, choices=ACTIONS),
    Param("name", help="scene name: scenes/<name>.toml", positional=True),
    Param("background", help="new: background asset, e.g. scenes/crypt-bg"),
    Param("horizon", "int", help="new: eye-level row"),
    Param("door", help="new: a door's base row and height in px, Y:H (e.g. 170:60)"),
    Param("camera", help="new: camera", choices=sc.CAMERAS, default="frontal"),
    Param("at", "float", help="scale/prompt: row where the feet or base touch the floor"),
    Param("height", "float", help="prompt: the prop's height in px (default: a person)"),
    Param("near", "float", help="sizes: nearest walkable row (default: bottom)"),
    Param("far", "float", help="sizes: farthest walkable row"),
    Param("state", "list", help="compose: layer=state, e.g. tomb=open"),
    Param("frame", "int", help="compose: animation frame", default=0),
    Param("gif", "bool", help="compose: also write the animated scene as a GIF"),
    Param("viewport", "int", help="compose: crop the view starting at this column"),
    Param("no_shadows", "bool", help="compose: leave out contact shadows"),
    Param("guides", "bool", help="compose: also write the scene with horizon, floor and bases"),
    Param("apply", "bool", help="analyze: write the estimated horizon to the scene file"),
)
@_guard
def cmd_scene(root: Path, a: dict[str, Any]) -> Outcome:
    project = _project(root)
    action, name = a["action"], a["name"]
    if not name:
        raise PwError("usage", "name the scene, e.g. pw scene show crypt", exit_code=2)
    if action == "new":
        if not (a["background"] and a["horizon"] is not None and a["door"]):
            raise PwError("usage", "new needs --background, --horizon and --door Y:H", exit_code=2)
        y, _, h = a["door"].partition(":")
        path = sc.new_scene(project, name, a["background"], horizon=a["horizon"],
                            door_y=int(y), door_h=int(h), camera=a["camera"])  # fmt: skip
        return Outcome(outputs=[str(path)], text=f"scene {name}: {path}")
    scene = sc.load_scene(project, name)
    if action == "show":
        data = scene.to_dict()
        return Outcome(data=data, text=f"{name}: {len(scene.layers)} layer(s), horizon "
                       f"{scene.horizon:g}, {scene.camera}")  # fmt: skip
    if action == "analyze":
        bg = sc.background_image(scene, project)
        vx, vy, agree = sc.vanishing_point(bg)
        est = sc.Scene(**{**scene.__dict__, "horizon": float(vy)})
        warnings = est.checks()
        data = {
            "vanishing_point": [vx, vy], "agreement": round(agree, 3), "horizon": vy,
            "was": scene.horizon, "camera_height_m": round(est.camera_height, 2),
        }  # fmt: skip
        if a["apply"]:
            sc.set_horizon(scene, vy)
        verb = "set" if a["apply"] else "estimated"
        text = (
            f"{name}: horizon {verb} at row {vy} (was {scene.horizon:g}); "
            f"camera {est.camera_height:.1f} m above the floor"
        )
        outputs = [str(scene.path)] if a["apply"] else []
        return Outcome(data=data, warnings=warnings, outputs=outputs, text=text)
    if action in ("scale", "prompt") and a["at"] is None:
        raise PwError("usage", f"{action} needs --at <row>", exit_code=2)
    if action == "scale":
        h = scene.person_height(a["at"])
        return Outcome(
            data={"at": a["at"], "person": h}, text=f"a person at row {a['at']:g}: {h:.1f} px"
        )
    if action == "sizes":
        sizes = sc.suggested_sizes(scene, a["near"], a["far"])
        rows = [{"height": s, "prompt": sc.size_prompt(s, sizes[0])} for s in sizes]
        return Outcome(
            data={"sizes": rows}, text="draw characters at " + ", ".join(f"{s} px" for s in sizes)
        )
    if action == "prompt":
        text = sc.scene_prompt(scene, a["at"], a["height"])
        return Outcome(data={"prompt": text}, text=text)
    states = _states(a["state"])
    out = sc.compose(scene, project, states=states, frame=a["frame"], shadows=not a["no_shadows"])
    paths = sc.write_outputs(
        scene,
        project,
        out,
        viewport_x=a["viewport"],
        gif=a["gif"],
        states=states,
        shadows=not a["no_shadows"],
    )
    if a["guides"]:
        g = project.export_dir / sc.SCENES_DIR / f"{name}-guides.png"
        Image.fromarray(sc.guides(scene, out), "RGBA").save(g)
        paths.append(g)
    return Outcome(outputs=[str(p) for p in paths], data=sc.layout(scene, out),
                   warnings=out.warnings, text=f"{name}: {paths[0]}")  # fmt: skip
