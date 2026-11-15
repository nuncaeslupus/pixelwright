// Play: the frames of a layered `.aseprite` version, with the file's own timing.
// Rigs, templates and cross-frame checks are M4; this is a player.
import { btn, drawGrid, esc, fitZoom, layer, loadImage, modes, paint, render, state } from "/static/app.js";


const pl = { frame: 0, playing: false, timer: null, tag: "", speed: 1, loop: true, onion: false, dir: 1, key: "" };
// Every frame shown while playing, with its time: read by the tests, handy when debugging timing.
window.pwPlayLog = [];

const images = new Map(); // url -> Promise<Image>, so playback never waits on the network twice
const image = (url) => { if (!images.has(url)) images.set(url, loadImage(url)); return images.get(url); };

const frames = () => state.frames || { frames: 0, durations: [], tags: [], urls: [] };

function range() {
  const tag = frames().tags.find((t) => t.name === pl.tag);
  return tag ? [tag.start, tag.end, tag.direction] : [0, frames().frames - 1, 0];
}

function stop() {
  clearTimeout(pl.timer);
  pl.playing = false;
}

function sync() {
  const key = `${state.route.asset}/${state.route.version}`;
  if (pl.key !== key) { stop(); Object.assign(pl, { key, frame: 0, tag: "", dir: 1 }); }
}

/** The frame after `f` in the tag's direction (0 forward, 1 reverse, 2-3 ping-pong). */
function next(f) {
  const [a, b, direction] = range();
  if (direction === 2 || direction === 3) {
    if (f + pl.dir > b || f + pl.dir < a) pl.dir = -pl.dir;
    return Math.min(b, Math.max(a, f + pl.dir));
  }
  const step = direction === 1 ? -1 : 1;
  const n = f + step;
  if (n > b || n < a) return pl.loop ? (step > 0 ? a : b) : null;
  return n;
}

function tick() {
  const n = next(pl.frame);
  if (n === null) { stop(); render(); return; }
  show(n);
  schedule();
}

function schedule() {
  pl.timer = setTimeout(tick, frames().durations[pl.frame] / pl.speed);
}

function show(f) {
  pl.frame = f;
  window.pwPlayLog.push({ frame: f, at: performance.now() });
  modes.play.draw();
  document.querySelectorAll(".fr").forEach((el) => el.classList.toggle("sel", +el.dataset.frame === f));
  const label = document.getElementById("frame-label");
  if (label) label.textContent = `${f + 1} / ${frames().frames}`;
}

function toggle() {
  if (pl.playing) { stop(); render(); return; }
  pl.playing = true;
  window.pwPlayLog = [];
  render();
  show(pl.frame);
  schedule();
}

function stepBy(d) {
  stop();
  const [a, b] = range();
  pl.frame = Math.min(b, Math.max(a, pl.frame + d));
  render();
}

modes.play.available = () => frames().frames > 1;
Object.assign(modes.play, {
  shortcuts: [["Space", "Play or pause"], [", .", "Previous or next frame"], ["O", "Loop"], ["N", "Onion skin"]],
  canvas() {
    sync();
    return '<canvas id="cv" aria-label="Animation frame"></canvas>';
  },
  async draw() {
    const f = frames();
    const view = ["color", "thumb"].includes(state.view) ? "" : `&view=${state.view}`;
    const img = await image(f.urls[pl.frame] + view);
    const cv = document.getElementById("cv");
    if (!cv) return;
    const z = fitZoom(img.width, img.height);
    paint(cv, img, z);
    if (pl.onion && !pl.playing && pl.frame > 0) layer(cv, await image(f.urls[pl.frame - 1] + view), 0.3);
    drawGrid(cv, img.width, img.height, z);
  },
  strip() {
    const f = frames();
    return `<div class="strip frames" aria-label="Frames">${f.urls.map((u, i) => btn("pl-frame", `Frame ${i + 1}, ${f.durations[i]} ms`, ", .", `
      <img alt="" src="${esc(u)}"><span class="mono">${f.durations[i]}ms</span>`, "th fr" + (i === pl.frame ? " sel" : ""), `data-frame="${i}"`)).join("")}</div>`;
  },
  bar() {
    return `${btn("pl-prev", "Previous frame", ",", "‹", "ib")}
      ${btn("pl-play", pl.playing ? "Pause" : "Play", "Space", pl.playing ? "❚❚" : "▶", "ib", `id="pl-play" aria-pressed="${pl.playing}"`)}
      ${btn("pl-next", "Next frame", ".", "›", "ib")}
      <span class="mono" id="frame-label">${pl.frame + 1} / ${frames().frames}</span><span class="vsep"></span>`;
  },
  issuesTop() {
    const f = frames();
    const tags = f.tags.map((t) => `<option value="${esc(t.name)}" ${t.name === pl.tag ? "selected" : ""}>${esc(t.name)} (${t.start + 1}-${t.end + 1})</option>`).join("");
    const speeds = [0.25, 0.5, 1, 2].map((s) => `<option value="${s}" ${s === pl.speed ? "selected" : ""}>${s}x</option>`).join("");
    return `<div class="newissue" aria-label="Playback">
      <div class="cap">Playback</div>
      <label class="prow">Tag <select id="pl-tag" title="Tag" aria-label="Tag"><option value="">All frames</option>${tags}</select></label>
      <label class="prow">Speed <select id="pl-speed" title="Speed" aria-label="Speed">${speeds}</select></label>
      <div class="prow">${btn("pl-loop", "Loop", "O", "Loop", "chip" + (pl.loop ? " on" : ""), `aria-pressed="${pl.loop}"`)}
        ${btn("pl-onion", "Onion skin: previous frame at 30% (when paused)", "N", "Onion skin", "chip" + (pl.onion ? " on" : ""), `aria-pressed="${pl.onion}"`)}</div></div>`;
  },
  onInput(t) {
    if (t.id === "pl-speed") pl.speed = +t.value;
    if (t.id === "pl-tag") { pl.tag = t.value; pl.frame = range()[0]; stop(); render(); }
  },
  actions: {
    "pl-frame": (el) => { stop(); pl.frame = +el.dataset.frame; render(); },
    "pl-play": toggle,
    "pl-prev": () => stepBy(-1),
    "pl-next": () => stepBy(1),
    "pl-loop": () => { pl.loop = !pl.loop; render(); },
    "pl-onion": () => { pl.onion = !pl.onion; render(); },
  },
  busy: () => pl.playing,
});

window.addEventListener("hashchange", () => { if (!location.hash.endsWith("/play")) stop(); });
document.addEventListener("change", (ev) => { if (state.route.mode === "play") modes.play.onInput(ev.target); });
document.addEventListener("keydown", (ev) => {
  if (state.route.mode !== "play" || ev.ctrlKey || ev.metaKey || ev.altKey) return;
  if (["TEXTAREA", "INPUT", "SELECT"].includes(ev.target.tagName)) return;
  const map = { " ": toggle, ",": () => stepBy(-1), ".": () => stepBy(1), o: modes.play.actions["pl-loop"], n: modes.play.actions["pl-onion"] };
  if (map[ev.key]) { ev.preventDefault(); map[ev.key](); }
});
