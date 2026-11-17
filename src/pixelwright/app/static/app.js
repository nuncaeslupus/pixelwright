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

// --- Asset screen -------------------------------------------------------------------
const AUTHOR = { script: "Scripts", ai: "AI", person: "You" };
let A = null; // asset screen state

async function openAsset(rel) {
  clearInterval(scanTimer);
  A = { rel, data: null, tool: "move", zoom: 0, view: "one", shown: null, selIssue: null,
        picked: new Set(), areas: [], peek: false, filter: "open" };
  await reloadAsset();
}

async function reloadAsset() {
  const res = await api().asset_detail(A.rel);
  if (!res.ok) return project();
  A.data = res;
  if (!A.shown || !res.versions.some((v) => v.name === A.shown)) A.shown = res.latest;
  drawAsset();
}

function versionImage(name) {
  const v = A.data.versions.find((x) => x.name === name);
  return v ? v.image : null;
}

function selectedFix() {
  const issue = A.data.issues.find((i) => i.id === A.selIssue);
  return issue ? issue.fixes.find((f) => f.state === "proposed") : null;
}

function scale() {
  const c = A.data.canvas;
  if (A.zoom) return A.zoom;
  const box = document.querySelector(".canvas");
  const w = box ? box.clientWidth - 40 : 800, h = box ? box.clientHeight - 60 : 500;
  const per = A.view === "side" ? 2 : 1;
  return Math.max(1, Math.floor(Math.min(w / per / c.width, h / c.height)));
}

function picture(src, label, withMarks) {
  const k = scale(), c = A.data.canvas;
  const marks = !withMarks ? "" : A.tool === "select"
    ? A.areas.map((b, n) => boxHtml(b, "sel", k, n)).join("")
    : A.data.issues.filter((i) => i.state === "open" && (!A.selIssue || i.id === A.selIssue))
        .flatMap((i) => i.areas.map((a) => boxHtml(a.box, i.author, k))).join("");
  return `<div class="pic" style="width:${c.width * k}px">${label ? `<span class="lbl">${esc(label)}</span>` : ""}
    <img alt="${esc(label || "image")}" src="${src}" style="width:${c.width * k}px;height:${c.height * k}px">${marks}</div>`;
}

function boxHtml(b, cls, k, n) {
  return `<div class="box ${cls}" ${n !== undefined ? `data-n="${n}"` : ""}
    style="left:${b[0] * k}px;top:${b[1] * k}px;width:${b[2] * k}px;height:${b[3] * k}px"></div>`;
}

function issueHtml(i) {
  const fix = i.fixes.find((f) => f.state === "proposed");
  const replies = i.replies.length ? `<div class="thread">${i.replies.map((r) =>
    `<div><b class="who ${r.by}">${AUTHOR[r.by]}</b> ${esc(r.message)}</div>`).join("")}</div>` : "";
  let acts = "";
  if (i.state === "open" && fix) {
    acts = `<label class="small"><input type="checkbox" class="pick" data-fix="${fix.id}" ${A.picked.has(fix.id) ? "checked" : ""}> pick</label>
      <button class="btn pri sm accept" data-fix="${fix.id}">Accept fix</button>
      <button class="btn ghost sm rejfix" data-fix="${fix.id}">Reject…</button>
      <button class="btn ghost sm reply">Reply…</button>`;
  } else if (i.state === "open") {
    acts = `<button class="btn ghost sm fixed">Mark fixed</button>
      <button class="btn ghost sm rejissue">Not an issue…</button>
      <button class="btn ghost sm reply">Reply…</button>`;
  }
  const state = i.state === "open" ? (i.target === "ai" && !fix ? "waiting on the AI" : fix ? "fix ready" : "open") : i.state;
  return `<div class="issue${A.selIssue === i.id ? " sel" : ""}" data-id="${i.id}">
    <div><b class="who ${i.author}">${AUTHOR[i.author]}</b> ${esc(i.message)}</div>
    <div class="dim small">${esc(state)} · on ${esc(i.version)}${i.replies.length ? ` · 💬 ${i.replies.length}` : ""}</div>
    ${replies}<div class="acts">${acts}</div><div class="error" hidden></div></div>`;
}

function drawAsset() {
  const d = A.data;
  crumb.textContent = "";
  const fix = selectedFix();
  const current = versionImage(A.shown);
  let stage;
  if (!current) {
    stage = `<div class="empty">No version yet: the scripts are still processing the input.</div>`;
  } else if (A.view === "side" && fix) {
    stage = picture(versionImage(d.latest), d.latest, false) + picture(fix.image, "with fix", false);
  } else if (fix && !A.peek) {
    stage = picture(fix.image, "", true);
  } else {
    stage = picture(current, "", true);
  }
  const issues = d.issues.filter((i) => A.filter === "all" || i.state === "open")
    .sort((a, b) => (b.fixes.some((f) => f.state === "proposed") - a.fixes.some((f) => f.state === "proposed")));
  const hint = A.tool === "select" ? "Drag to add an area · click one to remove · Esc clears"
    : fix ? "Showing the fix · hold Space or the image to compare" : "";
  view.innerHTML = `<div class="atop">
      <div class="row"><button class="btn" id="back" title="Back to the project" aria-label="Back">←</button>
        <span class="dim">${esc(d.asset.split("/").slice(0, -1).join(" / "))} /</span> <b>${esc(d.asset.split("/").pop())}</b>
        <span class="chip ${d.state}">${STATE[d.state]}</span></div>
      <div class="row"><button class="btn ghost" id="aseprite">Open in Aseprite</button>
        ${d.latest ? `<button class="btn pri" id="finish" title="Marks ${d.latest} as the final image and copies it to the export folder">Finish with ${d.latest}</button>` : ""}</div>
    </div>
    <div class="work">
      <section class="card stage">
        <div class="cbar">
          <div class="seg" role="group" aria-label="Tool">
            <button class="${A.tool === "move" ? "on" : ""}" data-tool="move" title="Move (H)">✋</button>
            <button class="${A.tool === "select" ? "on" : ""}" data-tool="select" title="Select areas (S)">⬚</button></div>
          <div class="seg"><button id="undo" title="Undo (Ctrl+Z)" ${d.can_undo ? "" : "disabled"}>↶</button>
            <button id="redo" title="Redo (Ctrl+Shift+Z)" ${d.can_redo ? "" : "disabled"}>↷</button></div>
          <div class="seg"><button class="${A.view === "one" ? "on" : ""}" data-view="one">One image</button>
            <button class="${A.view === "side" ? "on" : ""}" data-view="side" ${fix ? "" : "disabled"}>Side by side</button></div>
          <span class="hint">${hint}</span>
        </div>
        <div class="canvas" id="cv">${stage}
          <div class="zoombar"><button class="btn sm" id="zout">−</button><span class="small">${A.zoom ? A.zoom * 100 + "%" : "Fit"}</span>
          <button class="btn sm" id="zin">+</button></div></div>
        <div class="strip">${d.versions.map((v) => `<button class="ver${v.name === A.shown && !fix ? " on" : ""}" data-v="${v.name}">
          <img alt="" src="${v.image}"><span class="small">${v.name}${v.final ? " · final" : ""}</span>
          <span class="small star" data-star="${v.name}" title="Keep this version">${v.starred ? "★" : "☆"}</span></button>`).join("")}</div>
      </section>
      <aside class="card panel" aria-label="Issues">
        <div class="head"><b>Issues on ${esc(d.latest || "—")}</b>
          <div class="seg"><button class="${A.filter === "open" ? "on" : ""}" data-f="open">Open</button>
          <button class="${A.filter === "all" ? "on" : ""}" data-f="all">All</button></div></div>
        ${A.picked.size > 1 ? `<div class="ask"><span>${A.picked.size} fixes picked</span><button class="btn pri sm" id="acceptmany">Accept ${A.picked.size} fixes together</button></div>` : ""}
        <div class="issues">${issues.map(issueHtml).join("") || `<div class="empty">No open issues.</div>`}</div>
        <div class="ask"><b class="small">Ask the AI</b>
          <textarea class="field" id="askmsg" aria-label="Ask the AI" placeholder="What should the AI look at?"></textarea>
          <div class="row" style="justify-content:space-between"><span class="dim small">${A.areas.length ? `${A.areas.length} area(s) attached` : "Select areas to attach them"}</span>
          <button class="btn ai sm" id="send">Send to the AI</button></div><div class="error" hidden></div></div>
      </aside></div>`;
  wireAsset();
}

async function act(promise, where) {
  const r = await promise;
  if (!r.ok) { showError(where || view, r); return null; }
  await reloadAsset();
  return r;
}

function askReason(el, label, fn) {
  const box = el.querySelector(".acts");
  box.innerHTML = `<input class="field" placeholder="${label}" aria-label="${label}" style="flex:1">
    <button class="btn sm pri">Send</button><button class="btn sm">Cancel</button>`;
  const input = box.querySelector("input");
  input.focus();
  box.querySelector(".pri").onclick = (e) => { e.stopPropagation(); fn(input.value); };
  box.querySelectorAll(".btn")[1].onclick = (e) => { e.stopPropagation(); drawAsset(); };
  box.onclick = (e) => e.stopPropagation();
}

function wireAsset() {
  const d = A.data, rel = A.rel;
  view.querySelector("#back").onclick = () => { A = null; project(); };
  const fin = view.querySelector("#finish");
  if (fin) fin.onclick = () => act(api().finish(rel, d.latest));
  view.querySelector("#aseprite").onclick = () => act(api().open_in_aseprite(rel));
  view.querySelector("#undo").onclick = () => act(api().undo(rel));
  view.querySelector("#redo").onclick = () => act(api().redo(rel));
  view.querySelectorAll("[data-tool]").forEach((b) => { b.onclick = () => { A.tool = b.dataset.tool; drawAsset(); }; });
  view.querySelectorAll("[data-view]").forEach((b) => { b.onclick = () => { A.view = b.dataset.view; drawAsset(); }; });
  view.querySelectorAll("[data-f]").forEach((b) => { b.onclick = () => { A.filter = b.dataset.f; drawAsset(); }; });
  view.querySelector("#zin").onclick = () => { A.zoom = Math.min(32, (A.zoom || scale()) + 1); drawAsset(); };
  view.querySelector("#zout").onclick = () => { A.zoom = Math.max(0, (A.zoom || scale()) - 1); if (A.zoom <= 1) A.zoom = 0; drawAsset(); };
  view.querySelectorAll(".ver").forEach((b) => { b.onclick = () => { A.shown = b.dataset.v; A.selIssue = null; drawAsset(); }; });
  view.querySelectorAll(".star").forEach((s) => {
    s.onclick = (e) => { e.stopPropagation(); const v = d.versions.find((x) => x.name === s.dataset.star); act(api().star(rel, v.name, !v.starred)); };
  });
  view.querySelectorAll(".issue").forEach((el) => {
    const id = el.dataset.id;
    el.onclick = () => { A.selIssue = A.selIssue === id ? null : id; A.view = "one"; drawAsset(); };
    const q = (sel) => el.querySelector(sel);
    if (q(".pick")) q(".pick").onclick = (e) => { e.stopPropagation(); const f = e.target.dataset.fix; e.target.checked ? A.picked.add(f) : A.picked.delete(f); drawAsset(); };
    if (q(".accept")) q(".accept").onclick = (e) => { e.stopPropagation(); A.picked.clear(); A.selIssue = null; act(api().accept(rel, [e.target.dataset.fix]), el); };
    if (q(".rejfix")) q(".rejfix").onclick = (e) => { e.stopPropagation(); const f = e.target.dataset.fix; askReason(el, "Why not? (the AI reads this)", (r) => act(api().reject_fix(rel, f, r), el)); };
    if (q(".reply")) q(".reply").onclick = (e) => { e.stopPropagation(); askReason(el, "Reply to the AI", (m) => act(api().reply(rel, id, m), el)); };
    if (q(".fixed")) q(".fixed").onclick = (e) => { e.stopPropagation(); act(api().mark_fixed(rel, id), el); };
    if (q(".rejissue")) q(".rejissue").onclick = (e) => { e.stopPropagation(); askReason(el, "Why is it fine?", (r) => act(api().reject_issue(rel, id, r, false, "asset"), el)); };
  });
  const many = view.querySelector("#acceptmany");
  if (many) many.onclick = () => { const ids = [...A.picked]; A.picked.clear(); act(api().accept(rel, ids)); };
  view.querySelector("#send").onclick = async () => {
    const ask = view.querySelector(".panel .ask:last-child");
    const msg = view.querySelector("#askmsg").value;
    const r = await act(api().ask_ai(rel, msg, A.areas), ask);
    if (r) { A.areas = []; drawAsset(); }
  };
  wireCanvas();
}

function wireCanvas() {
  const pic = view.querySelector(".canvas .pic");
  if (!pic) return;
  const img = pic.querySelector("img");
  img.addEventListener("pointerdown", (e) => { if (A.tool === "move" && selectedFix()) { A.peek = true; drawAsset(); } });
  if (A.tool !== "select") return;
  const k = scale();
  let start = null, ghost = null;
  const at = (e) => { const r = img.getBoundingClientRect(); return [Math.floor((e.clientX - r.left) / k), Math.floor((e.clientY - r.top) / k)]; };
  pic.querySelectorAll(".box.sel").forEach((b) => { b.onclick = () => { A.areas.splice(+b.dataset.n, 1); drawAsset(); }; });
  img.addEventListener("pointerdown", (e) => {
    e.preventDefault(); start = at(e);
    ghost = Object.assign(document.createElement("div"), { className: "box sel" });
    pic.appendChild(ghost);
  });
  window.onpointermove = (e) => {
    if (!start) return;
    const p = at(e), x = Math.min(start[0], p[0]), y = Math.min(start[1], p[1]);
    Object.assign(ghost.style, { left: x * k + "px", top: y * k + "px", width: (Math.abs(p[0] - start[0]) + 1) * k + "px", height: (Math.abs(p[1] - start[1]) + 1) * k + "px" });
  };
  window.onpointerup = (e) => {
    if (!start) return;
    const p = at(e), c = A.data.canvas;
    const x = Math.max(0, Math.min(start[0], p[0])), y = Math.max(0, Math.min(start[1], p[1]));
    const w = Math.min(c.width - x, Math.abs(p[0] - start[0]) + 1), h = Math.min(c.height - y, Math.abs(p[1] - start[1]) + 1);
    start = null;
    if (w > 0 && h > 0) A.areas.push([x, y, w, h]);
    drawAsset();
  };
}

document.addEventListener("keydown", (e) => {
  if (!A || e.target.matches("input, textarea")) return;
  if (e.code === "Space" && selectedFix() && !A.peek) { e.preventDefault(); A.peek = true; drawAsset(); }
  else if (e.key === "Escape") { A.areas = []; A.selIssue = null; drawAsset(); }
  else if (e.key === "h") { A.tool = "move"; drawAsset(); }
  else if (e.key === "s") { A.tool = "select"; drawAsset(); }
  else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") act(api()[e.shiftKey ? "redo" : "undo"](A.rel));
});
document.addEventListener("keyup", (e) => { if (A && e.code === "Space" && A.peek) { A.peek = false; drawAsset(); } });
document.addEventListener("pointerup", () => { if (A && A.peek) { A.peek = false; drawAsset(); } });

window.addEventListener("pywebviewready", async () => {
  const opened = await api().list_assets();
  opened.ok ? project() : start();
});
