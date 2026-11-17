// App shell: start screen (open a folder, recent projects) and the project view.
// The core is called in-process through pywebview's js_api (window.pywebview.api).
"use strict";

const view = document.getElementById("view");
const crumb = document.getElementById("crumb");
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

function api() { return window.pywebview.api; }

function showError(where, res) {
  const box = where.querySelector(".error") || where.appendChild(Object.assign(document.createElement("div"), { className: "error" }));
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

// Placeholder until the Project screen (T61) replaces it.
async function project() {
  const res = await api().list_assets();
  if (!res.ok) return start();
  crumb.textContent = "/ " + res.project.name;
  view.innerHTML = `<div class="card"><b>${esc(res.project.name)}</b> <span class="dim">· ${res.assets.length} assets</span></div>`;
}

window.addEventListener("pywebviewready", async () => {
  const opened = await api().list_assets();
  opened.ok ? project() : start();
});
