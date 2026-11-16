// pixelwright viewer: the asset list and one asset (Look). Compare, Mark and Play register
// themselves in `modes`. Plain ES module, no build step; talks to the `pw view` JSON API.

export const token = document.querySelector('meta[name="pw-token"]').content;
const app = document.getElementById("app");
const keysDialog = document.getElementById("keys");

// -- small helpers -------------------------------------------------------------------
export const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

export async function api(path, body) {
  const init = body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-PW-Token": token },
    body: JSON.stringify(body),
  };
  const res = await fetch(path, init);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error ? data.error.message : res.statusText);
  return data;
}

const store = {
  get(key, fallback) {
    try { const v = localStorage.getItem("pw." + key); return v === null ? fallback : JSON.parse(v); } catch { return fallback; }
  },
  set(key, value) { try { localStorage.setItem("pw." + key, JSON.stringify(value)); } catch { /* private mode */ } },
};

const PATHS = {
  back: '<path d="M15 18l-6-6 6-6"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  bell: '<path d="M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
  keys: '<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M7 10h1M11 10h1M15 10h1M7 14h10"/>',
  theme: '<path d="M12 3a9 9 0 1 0 9 9 7 7 0 0 1-9-9z"/>',
  undo: '<path d="M9 14L4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>',
  grid: '<path d="M4 4h16v16H4zM4 10h16M4 16h16M10 4v16M16 4v16"/>',
  panel: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 4v16"/>',
  check: '<path d="M5 12l5 5 9-10"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
};
// What each rule checks, in the artist's words; issues store only the id.
export const RULES = {
  "R-PIX-1": "Off-palette or off-grid pixels", "R-PIX-2": "Ramps: flat or wrong hue shift",
  "R-PIX-3": "Orphan pixels and specks", "R-PIX-4": "Jagged lines", "R-PIX-5": "Banding",
  "R-PIX-6": "Pillow shading", "R-PIX-7": "Dither outside its zones", "R-PIX-8": "Anti-aliasing on the edge",
  "R-PIX-9": "Outline (selout)", "R-VAL-1": "Values: too many, or focus misplaced",
  "R-DEPTH-1": "Depth: far layers too strong", "R-READ-1": "Silhouette hard to read",
  "R-COLOR-1": "Sprite blends into the background", "R-STYLE-1": "Off style",
  "R-STYLE-3": "Effect or palette cycling", "R-STYLE-4": "Too much outline", "R-ANIM-4": "Animation inconsistent",
};
export const ruleName = (id) => RULES[id] || id;
export const icon = (name) => `<svg class="i" viewBox="0 0 24 24" aria-hidden="true">${PATHS[name]}</svg>`;

/** A visible control: its name and shortcut are on hover (title), never printed. */
export function btn(action, label, key, inner, cls = "ib", extra = "") {
  const title = key ? `${label} (${key})` : label;
  return `<button type="button" class="${cls}" data-action="${action}" title="${esc(title)}" aria-label="${esc(label)}" ${extra}>${inner}</button>`;
}

const STATUS_MARK = { pass: "✓", warn: "!", fail: "✕" };
const AUTHOR_LETTER = { human: "Y", claude: "C", check: "!" };
const when = (iso) => (iso ? new Date(iso).toLocaleString([], { dateStyle: "short", timeStyle: "short" }) : "");

// -- state and routing ----------------------------------------------------------------
export const state = {
  route: { asset: null, version: null, mode: "look" },
  list: null, asset: null, issues: null, history: null, report: null, frames: null, inbox: [],
  view: "color", zoom: 0, grid: store.get("grid", false), tab: "issues", side: true,
  selected: null, pop: null, notice: "", filters: { stage: "", kind: "", find: "" },
};

/** Modes of the asset screen. Look is here; the others add themselves (T29-T31). */
export const modes = {
  look: { label: "Look", key: "L", available: () => true },
  compare: { label: "Compare", key: "C", available: () => false },
  mark: { label: "Mark", key: "M", available: () => false },
  play: { label: "Play", key: "P", available: () => false },
};

function parseRoute() {
  const [asset, version, mode] = location.hash.replace(/^#\/?/, "").split("/");
  return { asset: asset || null, version: version || null, mode: mode && modes[mode] ? mode : "look" };
}

export function go(asset, version, mode = "look") {
  location.hash = asset ? `#/${asset}${version ? "/" + version : ""}${mode !== "look" ? "/" + mode : ""}` : "#/";
}

window.addEventListener("hashchange", () => {
  const next = parseRoute();
  if (next.asset !== state.route.asset) { state.asset = null; state.zoom = 0; }
  state.route = next;
  state.selected = null;
  state.pop = null;
  load();
});

// -- theme ------------------------------------------------------------------------------
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
}
applyTheme(store.get("theme", matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
function toggleTheme() {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  store.set("theme", next);
  applyTheme(next);
}

// -- data ------------------------------------------------------------------------------
async function fetchInbox() {
  state.inbox = (await api(inboxUrl())).items;
}

async function fetchAsset() {
  const id = state.route.asset;
  state.asset = await api(`/api/assets/${id}`);
  const versions = state.asset.versions.map((v) => v.version);
  if (!state.route.version || !versions.includes(state.route.version)) {
    state.route.version = versions[versions.length - 1] || null;
  }
  const v = state.route.version;
  if (!v) return;
  const [issues, history, report, frames] = await Promise.all([
    api(`/api/assets/${id}/issues?version=${v}`),
    api(`/api/assets/${id}/history`),
    api(`/api/assets/${id}/${v}/report`).catch(() => null),
    api(`/api/assets/${id}/${v}/frames`).catch(() => null),
  ]);
  Object.assign(state, { issues, history: history.history, report, frames });
  const seen = store.get("seen-versions", {});
  seen[`${id}/${v}`] = true;
  store.set("seen-versions", seen);
}

export async function load() {
  try {
    await fetchInbox();
    if (state.route.asset) await fetchAsset(); else state.list = (await api("/api/assets")).assets;
    state.notice = "";
  } catch (err) {
    state.notice = err.message;
  }
  render();
}

const inboxUrl = () => {
  const since = store.get("seen", null);
  return "/api/inbox" + (since ? `?since=${encodeURIComponent(since)}` : "");
};

/** Every 2 s: re-read what the screen shows and redraw only when something changed. */
async function poll() {
  if (document.hidden || state.pop || modes[state.route.mode].busy?.()) return;
  const { asset, version } = state.route;
  try {
    const inbox = (await api(inboxUrl())).items;
    const main = asset ? await api(`/api/assets/${asset}`) : (await api("/api/assets")).assets;
    const hist = asset && version ? (await api(`/api/assets/${asset}/history`)).history : null;
    const shown = [state.inbox, asset ? state.asset : state.list, asset && version ? state.history : null];
    if (JSON.stringify([inbox, main, hist]) !== JSON.stringify(shown)) await load();
  } catch { /* the server may be restarting; try again on the next tick */ }
}
setInterval(poll, 2000);

// -- shared chrome ------------------------------------------------------------------
function rightTools() {
  return `${btn("theme", "Light or dark theme", "T", icon("theme"))}
    ${btn("keys", "Help and keyboard shortcuts", "?", icon("keys"))}
    ${btn("inbox", "Inbox: what happened while you were away", "I", icon("bell") + (state.inbox.length ? '<span class="dot"></span>' : ""), "ib" + (state.pop === "inbox" ? " on" : ""), 'id="bell"')}`;
}

function popover() {
  if (state.pop === "inbox") {
    const items = state.inbox.length ? state.inbox.map((it) => `
      <div class="e"><span class="av a-${esc(it.author || "check")}">${AUTHOR_LETTER[it.author] || "·"}</span>
        <div>${btn("open-item", `Open ${it.asset} ${it.version || ""}`, "", `<strong>${esc(it.asset)}</strong> ${esc(it.event.replace("_", " "))} <span class="mono">${esc(it.version || "")}</span>`, "", `data-asset="${esc(it.asset)}" data-version="${esc(it.version || "")}"`)}
        <div class="d">${esc(it.note || "")} ${when(it.time)}</div></div></div>`).join("") : '<p class="muted">Nothing new.</p>';
    return `<div class="pop hist" role="dialog" aria-label="Inbox"><h3>Inbox</h3>${items}
      <div class="row">${btn("seen", "Mark all as seen", "", "Mark all seen", "btn")}</div></div>`;
  }
  if (state.pop === "approve" || state.pop === "reject") {
    const reject = state.pop === "reject";
    return `<div class="pop" role="dialog" aria-label="${reject ? "Reject" : "Approve"} ${esc(state.route.version)}">
      <h3>${reject ? "Reject" : "Approve"} <span class="mono">${esc(state.route.version)}</span></h3>
      <label class="cap" for="note">${reject ? "What should change? (required)" : "Note (optional)"}</label>
      <textarea id="note" placeholder="${reject ? "e.g. the door merges with the wall" : ""}"></textarea>
      <div class="err" id="pop-err"></div>
      <div class="row">${btn("cancel", "Cancel", "Esc", "Cancel", "btn")}
      ${btn("confirm", reject ? "Reject this version" : "Approve this version", "Ctrl+Enter", reject ? "Reject" : "Approve", "btn pri", 'id="confirm"')}</div></div>`;
  }
  if (state.pop === "menu") {
    const a = state.route.asset;
    const modeItems = Object.entries(modes).filter(([, m]) => m.available())
      .map(([id, m]) => ["mode", m.label, m.key, `data-mode="${id}"`]);
    const groups = [
      a && ["Version", [["approve", "Approve", "A"], ["reject", "Reject", "R"], ["undo", "Undo last decision", "Ctrl+Z"],
        ["prev", "Previous version", "←"], ["next", "Next version", "→"]]],
      a && ["Mode", modeItems],
      ["View", [...(a ? [["grid", "Pixel grid", "G"], ["panel", "Side panel", "H"]] : []), ["theme", "Light or dark theme", "T"]]],
      ["Go to", [...(a ? [["home", "All assets", "Esc"]] : []), ["inbox", "Inbox", "I"]]],
      ["Help", [["keys", "Keyboard shortcuts", "?"]]],
    ].filter(Boolean);
    const item = ([act, l, k, extra = ""]) =>
      btn(act, l, k, `<span>${esc(l)}</span><kbd>${esc(k)}</kbd>`, "mi", `role="menuitem" ${extra}`);
    return `<div class="pop menu" role="menu" aria-label="Menu" style="left:16px;right:auto">
      ${groups.map(([g, items]) => `<div class="cap">${g}</div>${items.map(item).join("")}`).join("")}</div>`;
  }
  return "";
}

// -- asset list ---------------------------------------------------------------------
function badgeClass(card) {
  if (/waiting/.test(card.status)) return "wait";
  if (/issue|fail/.test(card.status)) return "bad";
  if (card.stage === "approved" || card.stage === "final") return "good";
  return "";
}

function renderList() {
  const f = state.filters;
  const kinds = [...new Set((state.list || []).map((c) => c.kind))];
  const cards = (state.list || []).filter((c) =>
    (!f.stage || c.stage === f.stage) && (!f.kind || c.kind === f.kind) && (!f.find || c.id.includes(f.find.toLowerCase())));
  const seen = store.get("seen-versions", {});
  const opt = (value, label, current) => `<option value="${esc(value)}" ${value === current ? "selected" : ""}>${esc(label)}</option>`;
  app.innerHTML = `
    <header class="top"><div class="l">${btn("menu", "Menu: every command", "Ctrl+K", icon("menu"))}<span class="name">pixelwright</span></div><div></div>
      <div class="r">${rightTools()}</div></header>
    <div class="filters">
      <select id="f-stage" title="Stage" aria-label="Stage">${opt("", "All stages", f.stage)}${["draft", "approved", "final"].map((s) => opt(s, s, f.stage)).join("")}</select>
      <select id="f-kind" title="Kind" aria-label="Kind">${opt("", "All kinds", f.kind)}${kinds.map((k) => opt(k, k, f.kind)).join("")}</select>
      <input id="f-find" type="search" placeholder="Find by name" title="Find by name (/)" aria-label="Find by name" value="${esc(f.find)}">
      <span class="muted">${cards.length} of ${(state.list || []).length}</span>
    </div>
    ${cards.length ? `<main class="grid">${cards.map((c) => `
      <button type="button" class="card" data-action="open" data-asset="${esc(c.id)}" title="Open ${esc(c.id)} (Enter)" aria-label="Open ${esc(c.id)}">
        <div class="thumb">${c.thumbnail ? `<img alt="" src="${esc(c.thumbnail)}">` : ""}</div>
        <div class="nm"><span>${esc(c.id)}</span><span class="meta">${esc(c.kind)}</span></div>
        <div class="m">${c.newest && !seen[`${c.id}/${c.newest}`] ? '<span class="badge wait">new</span>' : ""}<span class="badge ${badgeClass(c)}">${esc(c.status)}</span></div>
      </button>`).join("")}</main>` : `<div class="empty">${state.list && state.list.length ? "No asset matches the filters." : "No assets yet. Create one with <code>pw new</code>."}</div>`}
    ${popover()}`;
  focusPop();
}

// -- asset screen (Look) -------------------------------------------------------------
export function current() {
  return state.asset && state.asset.versions.find((v) => v.version === state.route.version);
}

function topBar() {
  const v = current();
  const decided = v && (v.stage === "approved" || v.stage === "final");
  const modeButtons = Object.entries(modes).map(([id, m]) =>
    btn("mode", m.label, m.key, m.label, id === state.route.mode ? "on" : "", `data-mode="${id}" ${m.available() ? "" : "disabled"}`)).join("");
  return `<header class="top">
    <div class="l">${btn("menu", "Menu: every command", "Ctrl+K", icon("menu"))}${btn("home", "Back to all assets", "Esc", icon("back"))}
      <span class="name">${esc(state.asset.id)}</span><span class="meta">${esc(state.asset.spec.kind)} · <span class="mono">${esc(state.route.version || "no versions")}</span> · ${esc(v ? v.stage : "")}</span></div>
    <nav class="modes" aria-label="Mode">${modeButtons}</nav>
    <div class="r">${btn("undo", "Undo the last decision", "Ctrl+Z", icon("undo"))}
      ${btn("reject", "Reject this version", "R", icon("x") + "Reject", "pill no", v ? "" : "disabled")}
      ${btn("approve", decided ? "Approved: approve again with a note" : "Approve this version", "A", icon("check") + (decided ? "Approved" : "Approve"), "pill ok", v ? "" : "disabled")}
      <span class="vsep"></span>${rightTools()}</div></header>`;
}

function issuesPane() {
  const crit = state.issues && state.issues.critique;
  const list = (state.issues ? state.issues.issues : []);
  const verdict = crit ? `<div class="verdict"><span class="who t-claude"><span class="av a-claude">C</span>Claude's verdict</span><div>${esc(crit.verdict)}</div></div>` : "";
  const rows = list.length ? list.map((i) => btn("issue", `Show ${i.id} on the image`, "", `
      <span class="av a-${esc(i.author)}">${AUTHOR_LETTER[i.author] || "?"}</span>
      <span><strong>${esc(i.rule ? ruleName(i.rule) : i.id)}</strong> <span class="rule">${esc(i.rule ? i.rule + " · " + i.id : "")}</span><br>${esc(i.note)}</span>
      <span class="${i.status === "fixed" ? "fixed" : "rule"}">${i.status === "fixed" ? "fixed in " + esc(i.fixed_in) : "open"}</span>`,
    "issue" + (state.selected === i.id ? " sel" : ""), `data-issue="${esc(i.id)}"`)).join("") : '<p class="muted">No issues on this version.</p>';
  const top = modes[state.route.mode].issuesTop ? modes[state.route.mode].issuesTop() : "";
  return top + verdict + `<div class="cap">Issues</div>` + rows;
}

function checksPane() {
  const mode = modes[state.route.mode];
  if (mode.checks) return mode.checks();
  if (!state.report) return '<p class="muted">No checks yet. Run <code>pw check</code>.</p>';
  return state.report.results.map((r) => `<div class="crow"><span class="st ${esc(r.status)}" aria-label="${esc(r.status)}">${STATUS_MARK[r.status] || "?"}</span>
    <span>${esc(r.check)}</span><span class="m">${esc(typeof r.value === "number" ? +r.value.toFixed(3) : r.value ?? "")}</span></div>`).join("");
}

function historyLine(h) {
  if (h.event === "decision") {
    const failed = (h.measurements || []).filter((m) => m.status === "fail").length;
    return `${h.decision === "approve" ? "approved" : "rejected"} <span class="mono">${esc(h.version)}</span>${h.measurements && h.measurements.length ? ` · ${h.measurements.length} checks, ${failed} failing` : ""}`;
  }
  if (h.event === "decision_revert") return `undid the ${esc(h.decision)} of <span class="mono">${esc(h.version)}</span>`;
  const what = h.event === "step" ? h.step : h.event.replace("_", " ");
  return `${esc(what)} <span class="mono">${esc(h.version || "")}</span>`;
}

function historyPane() {
  return `<div class="hist">${(state.history || []).map((h) => `<div class="e"><span class="av a-${esc(h.author || "check")}">${AUTHOR_LETTER[h.author] || "·"}</span>
    <div><div>${historyLine(h)}</div>${h.note ? `<div>${esc(h.note)}</div>` : ""}<div class="d">${when(h.time)}</div></div></div>`).join("")}</div>`;
}

function sidePanel() {
  const open = (state.issues ? state.issues.issues : []).filter((i) => i.status === "open").length;
  const flagged = state.report ? state.report.results.filter((r) => r.status !== "pass").length : 0;
  const tab = (id, label, key, count, warn) => btn("tab", label, key, `${label}${count ? `<span class="n${warn ? " w" : ""}">${count}</span>` : ""}`, state.tab === id ? "on" : "", `data-tab="${id}" role="tab" aria-selected="${state.tab === id}"`);
  const pane = { issues: issuesPane, checks: checksPane, history: historyPane }[state.tab]();
  return `<aside class="side" ${state.side ? "" : "hidden"} aria-label="About this version">
    <div class="tabs" role="tablist">${tab("issues", "Issues", "1", open, false)}${tab("checks", "Checks", "2", flagged, true)}${tab("history", "History", "3", 0, false)}</div>
    <div class="pane" id="pane">${pane}</div></aside>`;
}

function strip() {
  const mode = modes[state.route.mode];
  if (mode.strip) return mode.strip();
  const seen = store.get("seen-versions", {});
  return `<div class="strip" aria-label="Versions">${state.asset.versions.map((v) => btn("version", `${v.version} · ${v.step} · ${v.stage}`, "← →", `
    <img alt="" src="/api/assets/${esc(state.asset.id)}/${v.version}/image.png">
    ${v.stage === "approved" || v.stage === "final" ? '<span class="okt">✓</span>' : ""}
    ${seen[`${state.asset.id}/${v.version}`] ? "" : '<span class="dot"></span>'}<span class="mono">${v.version}</span>`,
    "th" + (v.version === state.route.version ? " sel" : "") + (mode.thumbClass ? mode.thumbClass(v.version) : ""), `data-version="${v.version}"`)).join("")}</div>`;
}

function statusBar() {
  const v = current();
  const views = [["color", "Color"], ["gray", "Gray"], ["values", "Values"], ["silhouette", "Silhouette"], ["thumb", "25% thumb"]];
  return `<footer class="bar">
    <span id="pixel" class="mono">${esc(state.notice)}</span>
    <span class="sp"></span>${modes[state.route.mode].bar ? modes[state.route.mode].bar() : ""}
    <span>${v ? `${esc(v.stage)} · ${esc(v.step)}${v.parent ? ` from <span class="mono">${esc(v.parent)}</span>` : ""}` : ""}</span>
    <span class="vsep"></span>
    <select id="view" title="View (V)" aria-label="View">${views.map(([id, l]) => `<option value="${id}" ${id === state.view ? "selected" : ""}>${l}</option>`).join("")}</select>
    ${btn("grid", "Pixel grid (from 4x)", "G", icon("grid"), "ib" + (state.grid ? " on" : ""), `aria-pressed="${state.grid}"`)}
    ${btn("panel", "Show or hide the side panel", "H", icon("panel"), "ib" + (state.side ? " on" : ""))}
    <label class="slider" title="Zoom (+ −)"><input id="zoom" type="range" min="1" max="64" step="1" value="${state.zoom || 1}" aria-label="Zoom"><span class="mono" id="zoom-label">${state.zoom || 1}x</span></label>
  </footer>`;
}

// "What next?": the one next step for this asset, the command for it and why.
function hint() {
  const n = state.asset.next;
  if (!n) return "";
  return `<div class="hint" data-testid="next-hint"><b>Next: ${esc(n.step)}</b>
    <code>${esc(n.command)}</code><span>${esc(n.why)}</span></div>`;
}

function renderAsset() {
  if (!state.asset) { app.innerHTML = `<div class="empty">${esc(state.notice || "Loading…")}</div>`; return; }
  const empty = !state.route.version;
  const mode = modes[state.route.mode].available() ? modes[state.route.mode] : modes.look;
  const inner = mode.canvas ? mode.canvas() : '<canvas id="cv" aria-label="Version image"></canvas>';
  app.innerHTML = `${topBar()}
    <div class="body"><section class="work">
      <div class="canvas" id="stage">${empty ? '<div class="empty">No versions yet.</div>' : inner}</div>
      ${hint()}${strip()}${statusBar()}</section>${sidePanel()}</div>${popover()}`;
  if (!empty) redraw();
  focusPop();
}

// A freshly drawn dialog or menu takes the focus, so the keyboard acts inside it.
function focusPop() {
  if (document.activeElement?.closest(".pop")) return;
  document.querySelector(".pop textarea, .pop .mi")?.focus();
}

// -- canvas -----------------------------------------------------------------------------
const pixels = { data: null, w: 0, h: 0, key: "" };

export function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = src;
  });
}

/** Draw the current mode's canvas (Look: the version in the chosen view). */
export function redraw() {
  const mode = modes[state.route.mode];
  return (mode.available() && mode.draw ? mode.draw : drawImage)();
}

/** Integer zoom that fits an image of `w` x `h` in the canvas area. */
export function fitZoom(w, h, columns = 1) {
  const stage = document.getElementById("stage");
  if (!state.zoom && stage) {
    state.zoom = Math.min(64, Math.max(1, Math.floor(Math.min((stage.clientWidth - 24 * columns) / (w * columns), (stage.clientHeight - 24) / h))));
    const zoom = document.getElementById("zoom");
    if (zoom) { zoom.value = state.zoom; document.getElementById("zoom-label").textContent = state.zoom + "x"; }
  }
  return state.zoom || 1;
}

/** Checkerboard (for transparent pixels), then `img` scaled to the canvas, then the grid. */
export function paint(cv, img, z, alpha = 1, clip = null) {
  cv.width = img.width * z;
  cv.height = img.height * z;
  const ctx = cv.getContext("2d");
  ctx.imageSmoothingEnabled = false;
  const cell = Math.max(4, z * 2);
  for (let y = 0; y < cv.height; y += cell) for (let x = 0; x < cv.width; x += cell) {
    ctx.fillStyle = ((x + y) / cell) % 2 ? "#9a9a9a" : "#b0b0b0";
    ctx.fillRect(x, y, cell, cell);
  }
  layer(cv, img, alpha, clip);
  return ctx;
}

/** Draw `img` over what the canvas already shows; `clip` = [x0, x1) in canvas pixels. */
export function layer(cv, img, alpha = 1, clip = null) {
  const ctx = cv.getContext("2d");
  ctx.imageSmoothingEnabled = false;
  ctx.save();
  if (clip) { ctx.beginPath(); ctx.rect(clip[0], 0, clip[1] - clip[0], cv.height); ctx.clip(); }
  ctx.globalAlpha = alpha;
  ctx.drawImage(img, 0, 0, cv.width, cv.height);
  ctx.restore();
}

export function drawGrid(cv, w, h, z) {
  if (!state.grid || z < 4) return;
  const ctx = cv.getContext("2d");
  ctx.strokeStyle = "rgba(0,0,0,.18)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let x = 0; x <= w; x++) { ctx.moveTo(x * z + 0.5, 0); ctx.lineTo(x * z + 0.5, h * z); }
  for (let y = 0; y <= h; y++) { ctx.moveTo(0, y * z + 0.5); ctx.lineTo(w * z, y * z + 0.5); }
  ctx.stroke();
}

export async function drawImage() {
  const { asset, version } = state.route;
  const base = `/api/assets/${asset}/${version}/image.png`;
  const [shown, color] = await Promise.all([loadImage(state.view === "thumb" ? base : `${base}?view=${state.view}`), loadImage(base)]);
  const key = `${asset}/${version}`;
  if (pixels.key !== key) {
    const off = new OffscreenCanvas(color.width, color.height);
    const ctx = off.getContext("2d");
    ctx.drawImage(color, 0, 0);
    Object.assign(pixels, { data: ctx.getImageData(0, 0, color.width, color.height).data, w: color.width, h: color.height, key });
  }
  const cv = document.getElementById("cv");
  if (!cv) return;
  // 25% thumb: the image at a quarter of the zoom, to judge how it reads small
  const fit = fitZoom(shown.width, shown.height);
  const z = state.view === "thumb" ? Math.max(1, Math.round(fit / 4)) : fit;
  const ctx = paint(cv, shown, z);
  drawGrid(cv, shown.width, shown.height, z);
  await outlineIssue(ctx, z, shown.width, shown.height);
}

async function outlineIssue(ctx, z, w, h) {
  const issue = state.selected && state.issues && state.issues.issues.find((i) => i.id === state.selected);
  if (!issue) return;
  const color = getComputedStyle(document.documentElement).getPropertyValue(`--${issue.author === "human" ? "you" : issue.author}`).trim();
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  if (issue.region === "box") {
    const [x, y, bw, bh] = issue.box;
    ctx.strokeRect(x * z + 1, y * z + 1, bw * z - 2, bh * z - 2);
  } else if (issue.region === "image") {
    ctx.strokeRect(1, 1, w * z - 2, h * z - 2);
  } else if (issue.file) {
    const mask = await loadImage(`/assets/${state.route.asset}/${issue.file}`);
    const off = new OffscreenCanvas(w, h);
    const octx = off.getContext("2d");
    octx.drawImage(mask, 0, 0);
    const m = octx.getImageData(0, 0, w, h).data;
    ctx.fillStyle = color;
    ctx.globalAlpha = 0.35;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) if (m[(y * w + x) * 4] > 127) ctx.fillRect(x * z, y * z, z, z);
    ctx.globalAlpha = 1;
  }
}

function pixelInfo(ev) {
  const cv = ev.target;
  if (cv.id !== "cv" || !pixels.data || pixels.key !== `${state.route.asset}/${state.route.version}`) return;
  const z = state.zoom || 1;
  const x = Math.floor(ev.offsetX / z), y = Math.floor(ev.offsetY / z);
  if (x < 0 || y < 0 || x >= pixels.w || y >= pixels.h) return;
  const o = (y * pixels.w + x) * 4;
  const [r, g, b, a] = pixels.data.slice(o, o + 4);
  const hex = [r, g, b].map((c) => c.toString(16).padStart(2, "0")).join("");
  const index = state.asset.palette.indexOf(hex);
  const ramp = index >= 0 ? state.asset.ramps[String(index)] : null;
  document.getElementById("pixel").innerHTML = a === 0 ? `${x}, ${y} · transparent`
    : `${x}, ${y} <span class="swatch" style="background:#${hex}"></span> #${hex}${index >= 0 ? ` · index ${index}` : " · off palette"}${ramp ? ` · ${esc(ramp)}` : ""}`;
}

// -- actions ----------------------------------------------------------------------------
async function decide(choice) {
  const note = document.getElementById("note").value.trim();
  if (choice === "reject" && !note) {
    document.getElementById("pop-err").textContent = "Say what should change; it guides the next version.";
    return;
  }
  try {
    await api(`/api/assets/${state.route.asset}/${state.route.version}/decision`, { decision: choice, note });
    state.pop = null;
    state.tab = "history";
    await load();
  } catch (err) {
    document.getElementById("pop-err").textContent = err.message;
  }
}

async function undo() {
  if (!state.route.asset) return;
  if (modes[state.route.mode].undo?.()) return; // e.g. the last mask stroke
  try {
    const r = await api(`/api/assets/${state.route.asset}/revert`, {});
    state.notice = `Undid the ${r.reverted} of ${r.version}`;
    await load();
    state.notice = `Undid the ${r.reverted} of ${r.version}`;
    render();
  } catch (err) {
    state.notice = err.message;
    render();
  }
}

function step(delta) {
  if (!state.asset) return;
  const names = state.asset.versions.map((v) => v.version);
  const i = names.indexOf(state.route.version) + delta;
  if (i >= 0 && i < names.length) go(state.route.asset, names[i], state.route.mode);
}

// Tab and Shift+Tab cycle inside an open dialog or menu instead of leaving it.
function trapFocus(ev) {
  const pop = document.querySelector(".pop");
  const els = pop ? [...pop.querySelectorAll("button:not([disabled]), textarea, input, select")] : [];
  if (!els.length) return;
  const i = els.indexOf(document.activeElement);
  const next = ev.shiftKey ? (i <= 0 ? els.length - 1 : i - 1) : (i + 1) % els.length;
  ev.preventDefault();
  els[next].focus();
}

function togglePop(name) {
  state.pop = state.pop === name ? null : name;
  render();
}

const ACTIONS = {
  home: () => go(null),
  open: (el) => go(el.dataset.asset),
  "open-item": (el) => { state.pop = null; go(el.dataset.asset, el.dataset.version || null); },
  version: (el, ev) => {
    const mode = modes[state.route.mode];
    if (!(mode.onVersion && mode.onVersion(el.dataset.version, ev))) go(state.route.asset, el.dataset.version, state.route.mode);
  },
  mode: (el) => go(state.route.asset, state.route.version, el.dataset.mode),
  approve: () => togglePop("approve"),
  reject: () => togglePop("reject"),
  cancel: () => togglePop(null),
  confirm: () => decide(state.pop),
  undo,
  theme: toggleTheme,
  keys: showKeys,
  inbox: () => togglePop("inbox"),
  menu: () => togglePop("menu"),
  seen: async () => { store.set("seen", new Date().toISOString()); state.pop = null; await load(); },
  tab: (el) => { state.tab = el.dataset.tab; render(); },
  issue: (el) => { state.selected = state.selected === el.dataset.issue ? null : el.dataset.issue; render(); },
  grid: () => { state.grid = !state.grid; store.set("grid", state.grid); render(); },
  panel: () => { state.side = !state.side; render(); },
  prev: () => step(-1),
  next: () => step(1),
};

app.addEventListener("click", (ev) => {
  const el = ev.target.closest("[data-action]");
  if (!el || el.disabled) return;
  if (state.pop === "menu" && el.dataset.action !== "menu") state.pop = null;
  (ACTIONS[el.dataset.action] || modeAction(el.dataset.action))?.(el, ev);
});
const modeAction = (name) => modes[state.route.mode].actions?.[name];
app.addEventListener("mousemove", pixelInfo);
app.addEventListener("input", (ev) => {
  const t = ev.target;
  if (t.id === "zoom") { state.zoom = +t.value; document.getElementById("zoom-label").textContent = t.value + "x"; redraw(); }
  modes[state.route.mode].onInput?.(t);
  if (t.id === "f-find") { state.filters.find = t.value; renderList(); const f = document.getElementById("f-find"); f.focus(); f.setSelectionRange(t.value.length, t.value.length); }
});
app.addEventListener("change", (ev) => {
  const t = ev.target;
  if (t.id === "view") { state.view = t.value; redraw(); }
  if (t.id === "f-stage") { state.filters.stage = t.value; renderList(); }
  if (t.id === "f-kind") { state.filters.kind = t.value; renderList(); }
});

// -- keyboard ---------------------------------------------------------------------------
const SHORTCUTS = {
  list: [["Ctrl+K", "Menu: every command"], ["Enter", "Open the focused asset"], ["/", "Find by name"], ["I", "Inbox"], ["T", "Light or dark theme"], ["?", "This help"]],
  asset: [["A", "Approve"], ["R", "Reject"], ["Ctrl+Z", "Undo the last decision"], ["← →", "Previous or next version"],
    ["L C M P", "Look, Compare, Mark, Play"], ["1 2 3", "Issues, Checks, History"], ["H", "Show or hide the side panel"],
    ["V", "Next view (Color, Gray, Values, Silhouette, 25% thumb)"], ["G", "Pixel grid"], ["+ −", "Zoom"], ["Esc", "Close or go back"],
    ["Ctrl+K", "Menu: every command"], ["I", "Inbox"], ["T", "Light or dark theme"], ["?", "This help"]],
};

// Help: where this window sits in the loop, and what it does and does not do. The rows
// below are literal markup from our own source, so they are not escaped. The wording
// tracks `docs/guide/how-it-works.md`; change both together.
const LOOP = [
  ["1 · Sketch", "You draw the composition. <code>pw attach &lt;id&gt; sketch.png --as sketch</code>"],
  ["2 · Paint", "An image model paints 1-4 candidates. Their pixels are still fake. <code>pw generate</code>"],
  ["3 · Real pixels", "Find the grid, map to the palette, drop the specks. <code>pw snap</code> <code>pw quantize</code> <code>pw clean</code>"],
  ["4 · Measure", "The rules a machine can measure, and where they fail. <code>pw check</code>"],
  ["5 · Review", "<b>You are here.</b> Read the critique, compare against the last good version, mark what is wrong."],
  ["6 · Fix", "Repaint a marked region, redo a step inside it, or retouch it in Aseprite. <code>pw regen-region</code>"],
  ["7 · Approve", "<code>pw approve</code>, then <code>pw export</code> to the game."],
];

const WINDOW = [
  ["Nothing here edits an image", "This window shows versions and records what you say about them. An image changes only when a <code>pw</code> command or Aseprite writes a new version."],
  ["Approve and Reject are always there", "Every version is a decision waiting to be made, so the pair never goes away. Reject asks what should change; <code>Ctrl+Z</code> undoes the last decision."],
  ["How many versions", "No limit. Every step writes a new one and nothing is overwritten."],
  ["Who changes things", "You mark and decide. A provider paints, <code>pw</code> commands transform, Claude critiques. None of them approves."],
  ["Look, Compare, Mark, Play", "One image · two of them side by side, onion, swipe or difference · draw a region and file it as an issue · play an animation."],
  ["Seeing old and new together", "Compare, then Side by side. Both images share one zoom and one scroll, so they magnify together."],
  ["Marking something to be looked at", "Mark draws a region and saves it as an issue, with a rule and a note. Checks and Claude file issues the same way."],
];

const WORDS = [
  ["asset", "one game image - a background, a sprite"],
  ["version", "one image of an asset (<span class=\"mono\">v0001</span>, <span class=\"mono\">v0002</span>...); every step makes a new one"],
  ["stage", "where a version stands: draft, approved, rejected, final (exported)"],
  ["check", "an automatic measurement against a rule; <code>✓</code> pass, <code>!</code> warn, <code>✕</code> fail"],
  ["critique", "Claude's written review of a version, one section per complaint"],
  ["issue", "a region that needs fixing, drawn by you or filed by a check or a critique"],
  ["style guide", "the palette, rules and references every asset follows"],
  ["provider", "the image model that paints: replay (offline), comfyui (local GPU) or a paid API"],
];

function showKeys() {
  const table = (rows) => `<table>${rows.map(([k, d]) => `<tr><td>${esc(k)}</td><td>${esc(d)}</td></tr>`).join("")}</table>`;
  const rich = (rows) => `<table class="help">${rows.map(([k, d]) => `<tr><td>${k}</td><td>${d}</td></tr>`).join("")}</table>`;
  const mode = modes[state.route.mode];
  const extra = state.route.asset && mode.shortcuts ? `<h4>${esc(mode.label)}</h4>${table(mode.shortcuts)}` : "";
  const rules = Object.entries(RULES).map(([id, name]) => [`<span class="mono">${esc(id)}</span>`, esc(name)]);
  keysDialog.innerHTML = `<h3 tabindex="-1">Help</h3>
    <p>pixelwright turns a sketch into game-ready pixel art. An image model paints, code makes
    the pixels real and measures them, Claude reviews like an art director, you decide. This
    window is the deciding part.</p>
    <h4>The loop</h4>${rich(LOOP)}
    <h4>This window</h4>${rich(WINDOW)}
    <h4>Words</h4>${rich(WORDS)}
    <h4>Rule codes</h4>${rich(rules)}
    <h4>Keyboard shortcuts</h4>${extra}${state.route.asset && mode.shortcuts ? "<h4>Everywhere</h4>" : ""}${table(SHORTCUTS[state.route.asset ? "asset" : "list"])}
    <form method="dialog" style="text-align:right;margin-top:12px"><button class="btn" title="Close (Esc)">Close</button></form>`;
  keysDialog.showModal();
  // Long enough to scroll: the Close button would otherwise take focus and open it at the end.
  keysDialog.scrollTop = 0;
  keysDialog.querySelector("h3").focus();
}

document.addEventListener("keydown", (ev) => {
  const typing = ["TEXTAREA", "INPUT", "SELECT"].includes(ev.target.tagName);
  if (ev.key === "Tab" && state.pop) return trapFocus(ev);
  if (ev.key === "Escape") {
    if (keysDialog.open) return;
    if (state.pop) { state.pop = null; render(); } else if (!typing && state.route.asset) go(null);
    return;
  }
  if (typing) {
    if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey) && (state.pop === "approve" || state.pop === "reject")) decide(state.pop);
    return;
  }
  if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "z") { ev.preventDefault(); undo(); return; }
  if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "k") { ev.preventDefault(); togglePop("menu"); return; }
  if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
  const k = ev.key;
  if (["?", "t", "i"].includes(k)) ev.preventDefault();
  if (k === "?") return showKeys();
  if (k === "t") return toggleTheme();
  if (k === "i") return togglePop("inbox");
  if (!state.route.asset) {
    if (k === "/") { ev.preventDefault(); document.getElementById("f-find")?.focus(); }
    return;
  }
  const byKey = Object.entries(modes).find(([, m]) => m.key.toLowerCase() === k);
  if (byKey && byKey[1].available()) return go(state.route.asset, state.route.version, byKey[0]);
  const map = {
    a: () => current() && togglePop("approve"),
    r: () => current() && togglePop("reject"),
    ArrowLeft: () => step(-1),
    ArrowRight: () => step(1),
    1: () => ACTIONS.tab({ dataset: { tab: "issues" } }),
    2: () => ACTIONS.tab({ dataset: { tab: "checks" } }),
    3: () => ACTIONS.tab({ dataset: { tab: "history" } }),
    g: ACTIONS.grid,
    h: ACTIONS.panel,
    v: () => {
      const order = ["color", "gray", "values", "silhouette", "thumb"];
      state.view = order[(order.indexOf(state.view) + 1) % order.length];
      render();
    },
    "+": () => { state.zoom = Math.min(64, (state.zoom || 1) + 1); render(); },
    "-": () => { state.zoom = Math.max(1, (state.zoom || 1) - 1); render(); },
  };
  if (map[k]) { ev.preventDefault(); map[k](); }
});

// -- render -----------------------------------------------------------------------------
export function render() {
  if (state.route.asset) renderAsset(); else renderList();
}

state.route = parseRoute();
const MODE_MODULES = ["compare", "mark", "play"];
Promise.all(MODE_MODULES.map((m) => import(`/static/${m}.js`))).finally(load);
