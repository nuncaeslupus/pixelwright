// Mark: draw a complaint on the image in native pixels; it is saved as an issue (a mask,
// a rule, a note) so a fix can run only there (`R-CRIT-3`).
import { RULES, api, btn, drawImage, esc, load, loadImage, modes, render, state } from "/static/app.js";

const TOOLS = [["brush", "Brush", "B", '<path d="M4 20c3 0 5-2 5-5l9-9-3-3-9 9c-3 0-5 2-5 5z"/>'],
  ["rect", "Rectangle", "U", '<rect x="4" y="6" width="16" height="12" rx="1"/>'],
  ["fill", "Fill: same color, contiguous", "F", '<path d="M5 12l7-7 7 7-7 7z"/><path d="M19 15c1 2 2 3 2 4a2 2 0 0 1-4 0c0-1 1-2 2-4z"/>'],
  ["erase", "Erase", "E", '<path d="M8 20h12M4 15l9-9 6 6-7 7H8z"/>']];

const mk = { tool: "brush", size: 1, mask: null, w: 0, h: 0, key: "", undo: [], drag: null, rule: "", note: "", err: "" };

function reset() {
  mk.mask = mk.w ? new Uint8Array(mk.w * mk.h) : null;
  Object.assign(mk, { undo: [], rule: "", note: "", err: "", drag: null });
}

const marked = () => Boolean(mk.mask && mk.mask.some((v) => v));

function ensureMask() {
  const key = `${state.route.asset}/${state.route.version}`;
  if (mk.key !== key) { mk.key = key; mk.w = 0; mk.mask = null; mk.undo = []; }
}

function overlay() {
  const cv = document.getElementById("cv");
  if (!cv || !mk.mask) return;
  const z = state.zoom || 1;
  const ctx = cv.getContext("2d");
  ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--you").trim();
  ctx.globalAlpha = 0.45;
  for (let y = 0; y < mk.h; y++) for (let x = 0; x < mk.w; x++) if (mk.mask[y * mk.w + x]) ctx.fillRect(x * z, y * z, z, z);
  ctx.globalAlpha = 1;
  if (mk.drag && mk.tool === "rect") {
    const [x0, y0, x1, y1] = rectOf(mk.drag);
    ctx.strokeStyle = ctx.fillStyle;
    ctx.lineWidth = 2;
    ctx.strokeRect(x0 * z + 1, y0 * z + 1, (x1 - x0 + 1) * z - 2, (y1 - y0 + 1) * z - 2);
  }
}

const rectOf = (d) => [Math.min(d.x0, d.x1), Math.min(d.y0, d.y1), Math.max(d.x0, d.x1), Math.max(d.y0, d.y1)];

function cell(ev) {
  const z = state.zoom || 1;
  return [Math.floor(ev.offsetX / z), Math.floor(ev.offsetY / z)];
}

function dab(x, y, value) {
  const r0 = Math.floor((mk.size - 1) / 2);
  for (let dy = 0; dy < mk.size; dy++) for (let dx = 0; dx < mk.size; dx++) {
    const px = x - r0 + dx, py = y - r0 + dy;
    if (px >= 0 && py >= 0 && px < mk.w && py < mk.h) mk.mask[py * mk.w + px] = value;
  }
}

async function flood(x, y) {
  const img = await loadImage(`/api/assets/${state.route.asset}/${state.route.version}/image.png`);
  const off = new OffscreenCanvas(img.width, img.height);
  const octx = off.getContext("2d");
  octx.drawImage(img, 0, 0);
  const px = new Uint32Array(octx.getImageData(0, 0, img.width, img.height).data.buffer);
  const target = px[y * mk.w + x];
  const stack = [[x, y]];
  const seen = new Uint8Array(mk.w * mk.h);
  while (stack.length) {
    const [cx, cy] = stack.pop();
    const i = cy * mk.w + cx;
    if (cx < 0 || cy < 0 || cx >= mk.w || cy >= mk.h || seen[i] || px[i] !== target) continue;
    seen[i] = 1;
    mk.mask[i] = 1;
    stack.push([cx + 1, cy], [cx - 1, cy], [cx, cy + 1], [cx, cy - 1]);
  }
}

function down(ev) {
  if (ev.target.id !== "cv" || state.route.mode !== "mark" || ev.button !== 0) return;
  ev.preventDefault();
  const cv = ev.target;
  const z = state.zoom || 1;
  if (!mk.w) { mk.w = Math.round(cv.width / z); mk.h = Math.round(cv.height / z); mk.mask = new Uint8Array(mk.w * mk.h); }
  mk.undo.push(mk.mask.slice());
  const [x, y] = cell(ev);
  if (mk.tool === "fill") { flood(x, y).then(() => { mk.err = ""; render(); }); return; }
  mk.drag = { x0: x, y0: y, x1: x, y1: y };
  if (mk.tool !== "rect") dab(x, y, mk.tool === "erase" ? 0 : 1);
  modes.mark.draw();
}

function move(ev) {
  if (!mk.drag || ev.target.id !== "cv") return;
  const [x, y] = cell(ev);
  if (x === mk.drag.x1 && y === mk.drag.y1) return;
  if (mk.tool !== "rect") {
    // fill the gap between two pointer samples so fast strokes stay continuous
    const steps = Math.max(Math.abs(x - mk.drag.x1), Math.abs(y - mk.drag.y1));
    for (let s = 1; s <= steps; s++) {
      dab(Math.round(mk.drag.x1 + ((x - mk.drag.x1) * s) / steps), Math.round(mk.drag.y1 + ((y - mk.drag.y1) * s) / steps), mk.tool === "erase" ? 0 : 1);
    }
  }
  Object.assign(mk.drag, { x1: x, y1: y });
  modes.mark.draw();
}

function up() {
  if (!mk.drag) return;
  if (mk.tool === "rect") {
    const [x0, y0, x1, y1] = rectOf(mk.drag);
    for (let y = Math.max(0, y0); y <= Math.min(mk.h - 1, y1); y++) for (let x = Math.max(0, x0); x <= Math.min(mk.w - 1, x1); x++) mk.mask[y * mk.w + x] = 1;
  }
  mk.drag = null;
  render();
}

document.addEventListener("pointerdown", down);
document.addEventListener("pointermove", move);
document.addEventListener("pointerup", up);

async function save() {
  if (!marked()) { mk.err = "Mark the region first."; return render(); }
  if (!mk.note.trim()) { mk.err = "Say what is wrong there."; return render(); }
  const off = new OffscreenCanvas(mk.w, mk.h); // native size: white = inside
  const ctx = off.getContext("2d");
  const data = ctx.createImageData(mk.w, mk.h);
  mk.mask.forEach((v, i) => { if (v) data.data.set([255, 255, 255, 255], i * 4); });
  ctx.putImageData(data, 0, 0);
  const blob = await off.convertToBlob({ type: "image/png" });
  const png = btoa(String.fromCharCode(...new Uint8Array(await blob.arrayBuffer())));
  try {
    const out = await api(`/api/assets/${state.route.asset}/issues`, {
      png, rule: mk.rule, note: mk.note.trim(), version: state.route.version, author: "human",
    });
    reset();
    state.selected = out.issue.id;
    await load();
  } catch (err) {
    mk.err = err.message;
    render();
  }
}

modes.mark.available = () => Boolean(state.route.version);
Object.assign(modes.mark, {
  shortcuts: [["B U F E", "Brush, Rectangle, Fill, Erase"], ["[ ]", "Brush size"], ["Ctrl+S", "Save as an issue"], ["Ctrl+Z", "Undo the last stroke"]],
  canvas() {
    ensureMask();
    const tools = TOOLS.map(([id, label, key, path]) =>
      btn("mk-tool", label, key, `<svg class="i" viewBox="0 0 24 24" aria-hidden="true">${path}</svg>`, "ib" + (mk.tool === id ? " on" : ""), `data-tool="${id}" aria-pressed="${mk.tool === id}"`)).join("");
    const sizes = [1, 2, 3, 4, 6, 8].map((n) => `<option value="${n}" ${n === mk.size ? "selected" : ""}>${n}px</option>`).join("");
    return `<div class="tools" role="toolbar" aria-label="Mark tools">${tools}
      <select id="mk-size" title="Brush size ([ ])" aria-label="Brush size">${sizes}</select></div>
      <canvas id="cv" class="marking" aria-label="Version image: draw the region"></canvas>`;
  },
  async draw() {
    await drawImage();
    overlay();
  },
  issuesTop() {
    const opts = Object.entries(RULES).map(([r, name]) =>
      `<option value="${r}" ${r === mk.rule ? "selected" : ""}>${esc(name)} (${r})</option>`).join("");
    return `<form class="newissue" aria-label="New issue" onsubmit="return false">
      <div class="cap">New issue on <span class="mono">${esc(state.route.version)}</span></div>
      <select id="mk-rule" title="Rule" aria-label="Rule"><option value="">Other (no rule)</option>${opts}</select>
      <textarea id="mk-note" placeholder="What is wrong here, and what should change?" aria-label="Note">${esc(mk.note)}</textarea>
      <div class="err">${esc(mk.err)}</div>
      <div class="row">${btn("mk-discard", "Discard the marks", "", "Discard", "btn", marked() ? "" : "disabled")}
        ${btn("mk-save", "Save as an issue", "Ctrl+S", "Save", "btn pri")}</div></form>`;
  },
  onInput(t) {
    if (t.id === "mk-note") mk.note = t.value;
    if (t.id === "mk-rule") mk.rule = t.value;
    if (t.id === "mk-size") mk.size = +t.value;
  },
  busy: () => marked() || Boolean(mk.note) || Boolean(mk.drag),
  undo() {
    if (!mk.undo.length) return false;
    mk.mask = mk.undo.pop();
    render();
    return true;
  },
  actions: {
    "mk-tool": (el) => { mk.tool = el.dataset.tool; render(); },
    "mk-discard": () => { reset(); render(); },
    "mk-save": save,
  },
});

const KEY_TOOL = { b: "brush", u: "rect", f: "fill", e: "erase" };
document.addEventListener("change", (ev) => { if (state.route.mode === "mark") modes.mark.onInput(ev.target); });
document.addEventListener("keydown", (ev) => {
  if (state.route.mode !== "mark") return;
  if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "s") { ev.preventDefault(); save(); return; }
  if (ev.ctrlKey || ev.metaKey || ev.altKey || ["TEXTAREA", "INPUT", "SELECT"].includes(ev.target.tagName)) return;
  if (KEY_TOOL[ev.key]) { ev.preventDefault(); mk.tool = KEY_TOOL[ev.key]; render(); }
  if (ev.key === "[" || ev.key === "]") {
    const sizes = [1, 2, 3, 4, 6, 8];
    mk.size = sizes[Math.max(0, Math.min(sizes.length - 1, sizes.indexOf(mk.size) + (ev.key === "]" ? 1 : -1)))];
    render();
  }
});

window.addEventListener("hashchange", () => {
  if (location.hash.endsWith("/mark")) state.tab = "issues";
});
