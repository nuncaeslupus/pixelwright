// App shell: start screen (open a folder, recent projects) and the project view.
// The core is called in-process through pywebview's js_api (window.pywebview.api).
"use strict";

const view = document.getElementById("view");
const crumb = document.getElementById("crumb");
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

function api() { return window.pywebview.api; }

function showError(where, res) {
  const box = where.querySelector(".error") || where.appendChild(Object.assign(document.createElement("div"), { className: "error" }));
  box.hidden = false;
  box.textContent = res.error;
}

async function start() {
  crumb.textContent = "";
  const res = await api().recent_projects();
  const items = (res.projects || []).map((p) =>
    `<div class="recent" data-path="${esc(p.path)}"><span>${esc(p.name)}</span><span class="dim">${esc(p.path)}</span></div>`).join("");
  view.innerHTML = `<div class="start card">
    <b style="font-size:20px">Turn any image into clean pixel art</b>
    <div><button class="btn pri" id="open">Open a project folder…</button></div>
    ${items ? `<div class="dim small">Recent</div>${items}` : ""}</div>`;
  const card = view.querySelector(".card");
  view.querySelector("#open").onclick = async () => {
    const r = await api().pick_and_open();
    if (!r.ok) return showError(card, r);
    if (!r.cancelled) project();
  };
  view.querySelectorAll(".recent").forEach((el) => {
    el.onclick = async () => {
      const r = await api().open_project(el.dataset.path);
      r.ok ? project() : showError(card, r);
    };
  });
}

// --- Project screen -----------------------------------------------------------------
const STATE = { processing: "Processing", review: "In review", finished: "Finished" };
const ACTOR = { you: "Y", ai: "AI", scripts: "S", none: "✓" };
const WHO = { you: "You", ai: "AI", scripts: "Scripts" };
let filter = { kind: "all", value: null };
let scanTimer = null;

function matches(a) {
  if (filter.kind === "actor") return a.next.actor === filter.value;
  if (filter.kind === "state") return a.state === filter.value;
  if (filter.kind === "category") return a.category === filter.value;
  return true;
}

function navItem(label, n, kind, value) {
  const on = filter.kind === kind && filter.value === value;
  return `<button class="navi${on ? " on" : ""}" data-kind="${kind}" data-value="${esc(value ?? "")}">
    <span>${label}</span><span class="n">${n}</span></button>`;
}

function card(a) {
  const img = a.thumb ? `<img alt="" src="${a.thumb}">` : `<span class="dim">no version yet</span>`;
  return `<button class="asset" data-asset="${esc(a.asset)}" aria-label="Open ${esc(a.asset)}">
    <div class="thumb">${img}</div>
    <div class="meta"><div class="row" style="justify-content:space-between">
      <b>${esc(a.asset.split("/").pop())}</b><span class="chip ${a.state}">${STATE[a.state]}</span></div>
      <div class="next"><span class="av ${a.next.actor}">${ACTOR[a.next.actor]}</span>
      <span class="step">${esc(a.next.text)}</span></div></div></button>`;
}

async function project() {
  const res = await api().list_assets();
  if (!res.ok) return start();
  crumb.textContent = "/ " + res.project.name;
  const all = res.assets;
  const count = (f) => all.filter(f).length;
  const newOnes = count((a) => a.state === "review" && a.next.actor !== "ai");
  const shown = all.filter(matches);
  view.innerHTML = `<div class="layout">
    <nav class="card side" aria-label="Filters">
      ${navItem("All assets", all.length, "all", null)}
      <div class="h">Waiting on</div>
      ${["you", "ai", "scripts"].map((w) => navItem(WHO[w], count((a) => a.next.actor === w), "actor", w)).join("")}
      <div class="h">State</div>
      ${Object.keys(STATE).map((s) => navItem(STATE[s], count((a) => a.state === s), "state", s)).join("")}
      <div class="h">Categories</div>
      ${res.categories.map((c) => navItem(esc(c), count((a) => a.category === c), "category", c)).join("")}
    </nav>
    <section class="card main">
      <div class="bar"><div><b style="font-size:16px">${filter.kind === "all" ? "All assets" : esc(filter.value)}</b>
        <span class="dim">· ${shown.length}</span></div>
        <div class="row"><button class="btn ai" id="review">Review all new with AI · ${newOnes}</button>
        <button class="btn pri" id="add">+ Add images</button></div></div>
      <div class="error" hidden></div>
      ${shown.length ? `<div class="grid">${shown.map(card).join("")}</div>`
        : `<div class="empty">No assets here yet. Add images, or save them into a category folder.</div>`}
    </section></div>`;
  view.querySelectorAll(".navi").forEach((el) => {
    el.onclick = () => { filter = { kind: el.dataset.kind, value: el.dataset.value || null }; project(); };
  });
  view.querySelectorAll(".asset").forEach((el) => { el.onclick = () => openAsset(el.dataset.asset); });
  const main = view.querySelector(".main");
  view.querySelector("#review").onclick = async () => {
    const r = await api().review_all_new();
    r.ok ? project() : showError(main, r);
  };
  view.querySelector("#add").onclick = () => addDialog(res.categories, main);
  watch();
}

function addDialog(categories, where) {
  let chosen = (filter.kind === "category" && filter.value) || categories[0] || "";
  const box = document.createElement("div");
  const draw = () => {
    box.innerHTML = `<div class="dimmer"></div><div class="card dialog" role="dialog" aria-label="Add images">
      <b style="font-size:16px">Add images</b><div class="small"><b>Category</b></div>
      <div class="row">${categories.map((c) => `<button class="btn ${c === chosen ? "pri" : "ghost"} cat" data-c="${esc(c)}">${esc(c)}</button>`).join("")}
        <input class="field" id="newcat" placeholder="+ New category…" aria-label="New category"></div>
      <div class="dim small">The category sets canvas size, palette and checks. Each image becomes its own asset; the scripts clean and check it right away.</div>
      <div class="error" hidden></div>
      <div class="row" style="justify-content:flex-end"><button class="btn" id="cancel">Cancel</button>
        <button class="btn pri" id="choose">Choose images…</button></div></div>`;
    box.querySelectorAll(".cat").forEach((el) => { el.onclick = () => { chosen = el.dataset.c; draw(); }; });
    box.querySelector("#cancel").onclick = () => box.remove();
    box.querySelector(".dimmer").onclick = () => box.remove();
    box.querySelector("#choose").onclick = async () => {
      const typed = box.querySelector("#newcat").value.trim();
      const r = await api().pick_and_add(typed || chosen);
      if (!r.ok) return showError(box.querySelector(".dialog"), r);
      box.remove();
      if (!r.cancelled) project();
    };
  };
  draw();
  document.body.appendChild(box);
  document.addEventListener("keydown", function esc_(e) {
    if (e.key === "Escape") { box.remove(); document.removeEventListener("keydown", esc_); }
  });
}

function watch() {
  clearInterval(scanTimer);
  scanTimer = setInterval(async () => {
    if (!document.querySelector(".main") || document.querySelector(".dialog")) return;
    const r = await api().scan();
    if (r.ok && r.added.length) project();
  }, 3000);
}

// Placeholder until the Asset screen (T62) replaces it.
async function openAsset(rel) {
  clearInterval(scanTimer);
  crumb.textContent = "/ " + rel;
  view.innerHTML = `<div class="card"><button class="btn" id="back">←</button> <b>${esc(rel)}</b></div>`;
  view.querySelector("#back").onclick = () => project();
}

window.addEventListener("pywebviewready", async () => {
  const opened = await api().list_assets();
  opened.ok ? project() : start();
});
