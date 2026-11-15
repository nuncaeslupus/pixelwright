// Compare: is the selected version (B) better than the previous best (A)? (`R-CRIT-2`)
// A defaults to the newest approved version; shift-click a thumbnail to choose A.
import { api, btn, drawGrid, esc, fitZoom, layer, load, loadImage, modes, paint, render, state } from "/static/app.js";

const VIEWS = [["side", "Side by side", "S"], ["onion", "Onion", "O"], ["swipe", "Swipe", "W"], ["diff", "Difference", "D"]];
const CAND = ["cand", "Candidates", "C"];
const cmp = { a: null, asset: null, view: "side", mix: 50, diff: null, diffKey: "", touched: false };

/** Candidates: B and its siblings from the same `pw generate` call (same request hash). */
export function candidates() {
  const own = state.asset.versions.find((v) => v.version === state.route.version);
  if (!own || !own.request_hash) return [];
  const same = state.asset.versions.filter((v) => v.request_hash === own.request_hash);
  return same.length > 1 ? same : [];
}

function candidatesCanvas(cands) {
  const figs = cands.map((c) => `<figure class="cmp"><canvas id="cv-c-${esc(c.version)}" aria-label="Candidate ${esc(c.version)}"></canvas>
    <figcaption><span class="mono">${esc(c.version)}</span> · ${esc(c.stage)}
    ${btn("cmp-pick", `Pick ${c.version}, reject the other candidates`, "", "Pick", "tb", `data-v="${esc(c.version)}"`)}</figcaption></figure>`).join("");
  return `<div class="pair" id="pair">${figs}</div>`;
}

/** A: the chosen one, else the newest approved version other than B, else B's parent. */
export function versionA() {
  const versions = state.asset.versions;
  const b = state.route.version;
  if (cmp.asset !== state.asset.id) Object.assign(cmp, { a: null, asset: state.asset.id });
  if (cmp.a && cmp.a !== b && versions.some((v) => v.version === cmp.a)) return cmp.a;
  const approved = versions.filter((v) => (v.stage === "approved" || v.stage === "final") && v.version !== b);
  if (approved.length) return approved[approved.length - 1].version;
  const own = versions.find((v) => v.version === b);
  if (own && own.parent) return own.parent;
  const i = versions.findIndex((v) => v.version === b);
  return versions[i > 0 ? i - 1 : 1]?.version || null;
}

async function diffData(a, b) {
  const key = `${state.asset.id}/${a}/${b}`;
  if (cmp.diffKey !== key) {
    cmp.diff = await api(`/api/assets/${state.asset.id}/diff?a=${a}&b=${b}`);
    cmp.diffKey = key;
  }
  return cmp.diff;
}

const url = (v) => `/api/assets/${state.asset.id}/${v}/image.png?view=${state.view === "thumb" ? "color" : state.view}`;

modes.compare.available = () => Boolean(state.asset && state.asset.versions.length > 1);
Object.assign(modes.compare, {
  shortcuts: [["C S O W D", "Candidates, Side by side, Onion, Swipe, Difference"], ["[ ]", "Onion opacity or swipe position"], ["Shift+click", "Choose version A"]],
  canvas() {
    const a = versionA();
    const cands = candidates();
    if (cands.length && !cmp.touched) cmp.view = "cand";
    if (!cands.length && cmp.view === "cand") cmp.view = "side";
    const seg = (cands.length ? [CAND, ...VIEWS] : VIEWS).map(([id, label, key]) => btn("cmp-view", label, key, label, cmp.view === id ? "on" : "", `data-view="${id}"`)).join("");
    const pair = cmp.view === "side"
      ? `<figure class="cmp"><canvas id="cv-a" aria-label="A ${esc(a)}"></canvas><figcaption>A · <span class="mono">${esc(a)}</span></figcaption></figure>
         <figure class="cmp"><canvas id="cv" aria-label="B ${esc(state.route.version)}"></canvas><figcaption>B · <span class="mono">${esc(state.route.version)}</span></figcaption></figure>`
      : `<figure class="cmp"><canvas id="cv-mix" aria-label="${esc(a)} and ${esc(state.route.version)}"></canvas>
         <figcaption>A <span class="mono">${esc(a)}</span> · B <span class="mono">${esc(state.route.version)}</span></figcaption></figure>`;
    if (cmp.view === "cand") return `<nav class="seg" aria-label="Compare view">${seg}</nav>${candidatesCanvas(cands)}`;
    return `<nav class="seg" aria-label="Compare view">${seg}</nav><div class="pair" id="pair">${pair}</div>`;
  },
  async draw() {
    if (cmp.view === "cand") {
      const cands = candidates();
      const imgs = await Promise.all(cands.map((c) => loadImage(url(c.version))));
      const z = fitZoom(imgs[0].width, imgs[0].height, cands.length);
      cands.forEach((c, i) => {
        const cv = document.getElementById(`cv-c-${c.version}`);
        if (cv) { paint(cv, imgs[i], z); drawGrid(cv, imgs[i].width, imgs[i].height, z); }
      });
      return;
    }
    const a = versionA();
    const b = state.route.version;
    if (!a) return;
    const [ia, ib] = await Promise.all([loadImage(url(a)), loadImage(url(b))]);
    const z = fitZoom(ib.width, ib.height, cmp.view === "side" ? 2 : 1);
    if (cmp.view === "side") {
      for (const [id, img] of [["cv-a", ia], ["cv", ib]]) {
        const cv = document.getElementById(id);
        if (cv) { paint(cv, img, z); drawGrid(cv, img.width, img.height, z); }
      }
      return;
    }
    const cv = document.getElementById("cv-mix");
    if (!cv) return;
    if (cmp.view === "diff") {
      const d = await diffData(a, b);
      const di = await loadImage(d.image); // the diff overlay is rendered at 4x
      paint(cv, di, (z * ib.width) / di.width);
    } else {
      paint(cv, ia, z);
      if (cmp.view === "onion") layer(cv, ib, cmp.mix / 100);
      else layer(cv, ib, 1, [0, Math.round(cv.width * cmp.mix / 100)]);
    }
    drawGrid(cv, ib.width, ib.height, z);
  },
  bar() {
    if (cmp.view !== "onion" && cmp.view !== "swipe") return "";
    const label = cmp.view === "onion" ? "B opacity" : "Swipe position";
    return `<label class="slider" title="${label} ([ ])"><span>${label}</span><input id="cmp-mix" type="range" min="0" max="100" value="${cmp.mix}" aria-label="${label}"></label><span class="vsep"></span>`;
  },
  onInput(t) {
    if (t.id === "cmp-mix") { cmp.mix = +t.value; modes.compare.draw(); }
  },
  thumbClass(v) {
    return v === versionA() ? " a" : "";
  },
  onVersion(v, ev) {
    if (!ev || !ev.shiftKey) return false;
    if (v !== state.route.version) { cmp.a = v; render(); }
    return true;
  },
  checks() {
    const a = versionA();
    if (!cmp.diff || cmp.diffKey !== `${state.asset.id}/${a}/${state.route.version}`) {
      diffData(a, state.route.version).then(render).catch(() => {});
      return '<p class="muted">Comparing…</p>';
    }
    const d = cmp.diff;
    const cell = (x) => (x ? `<span class="st ${esc(x.status)}" aria-label="${esc(x.status)}">${{ pass: "✓", warn: "!", fail: "✕" }[x.status] || "?"}</span>` : '<span class="muted">—</span>');
    const rows = d.checks.map((c) => `<div class="crow"><span>${esc(c.check)}</span><span class="m">${cell(c.a)} → ${cell(c.b)}</span></div>`).join("");
    const area = d.bbox && d.bbox.length ? `${d.bbox[2]}×${d.bbox[3]} at ${d.bbox[0]},${d.bbox[1]}` : "none";
    return `<div class="cap">Checks <span class="mono">${esc(a)}</span> → <span class="mono">${esc(state.route.version)}</span></div>
      ${rows || '<p class="muted">Run <code>pw check</code> on both versions to compare them.</p>'}
      <div class="cap" style="margin-top:14px">Difference</div>
      <div class="crow"><span>Changed pixels</span><span class="m" id="changed">${d.changed} (${(d.share * 100).toFixed(1)}%)</span></div>
      <div class="crow"><span>Colors used</span><span class="m">${d.colors[0]} → ${d.colors[1]}</span></div>
      <div class="crow"><span>Area changed</span><span class="m">${area}</span></div>`;
  },
  actions: {
    "cmp-view": (el) => { cmp.view = el.dataset.view; cmp.touched = true; render(); },
    "cmp-pick": async (el) => {
      const pick = el.dataset.v;
      for (const c of candidates()) {
        if (c.version === pick) continue;
        await api(`/api/assets/${state.asset.id}/${c.version}/decision`, { decision: "reject", note: `not picked: chose ${pick}` });
      }
      location.hash = `#/${state.asset.id}/${pick}/compare`;
      await load();
    },
  },
  keys: { s: "side", o: "onion", w: "swipe", d: "diff", c: "cand" },
});

document.addEventListener("keydown", (ev) => {
  if (state.route.mode !== "compare" || ev.ctrlKey || ev.metaKey || ev.altKey) return;
  if (["TEXTAREA", "INPUT", "SELECT"].includes(ev.target.tagName)) return;
  const view = modes.compare.keys[ev.key];
  if (view && (view !== "cand" || candidates().length)) { ev.preventDefault(); cmp.view = view; cmp.touched = true; render(); }
  if (ev.key === "[" || ev.key === "]") {
    cmp.mix = Math.max(0, Math.min(100, cmp.mix + (ev.key === "]" ? 10 : -10)));
    render();
  }
});
